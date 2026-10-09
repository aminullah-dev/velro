"""Repository base.

Two things happen here so that no individual query can forget them:
soft-delete filtering, and a bounded default limit. A repository method that
returns an unbounded list is a production incident waiting for the table to
grow.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from sqlalchemy import Select, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from infrastructure.db.base import Auditable
from shared.errors import NotFoundError

R = TypeVar("R", bound=Auditable)

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


class SqlRepository(Generic[R]):
    model: type[R]
    not_found_code: str

    def __init__(self, session: Session) -> None:
        self.session = session

    # -- querying ---------------------------------------------------------

    def _base(self) -> Select[tuple[R]]:
        """Every read starts here, so ``deleted_at IS NULL`` cannot be omitted."""
        return select(self.model).where(self.model.deleted_at.is_(None))

    def find(self, id: str) -> R | None:
        """Returns None when absent. Never mixed with ``get``."""
        return self.session.scalars(self._base().where(self.model.id == id)).one_or_none()

    def get(self, id: str) -> R:
        """Raises when absent. Never mixed with ``find``."""
        row = self.find(id)
        if row is None:
            raise NotFoundError(self.not_found_code, id=id)
        return row

    def lock(self, id: str) -> R | None:
        """The row, held FOR UPDATE until the transaction commits or rolls back.

        For the writers of contended state: a status checked on an unlocked row
        is true only at the instant of the read, and two transactions can both
        pass the same check before either commits. Reading through this instead
        serialises them -- the second blocks, then sees what the first wrote.

        On SQLite the FOR UPDATE is dropped by the dialect; the database-wide
        write lock stands in, which is the same stance seats.py takes.
        """
        return self.session.scalars(
            self._base().where(self.model.id == id).with_for_update()
        ).one_or_none()

    def find_by(self, **criteria: Any) -> R | None:
        stmt = self._base()
        for column, value in criteria.items():
            stmt = stmt.where(getattr(self.model, column) == value)
        return self.session.scalars(stmt).first()

    def by_ids(self, ids) -> list[R]:
        """Several rows in one query.

        Screens that render a list almost always need something joined to each
        row; without this each one becomes its own round trip, which on a rural
        connection is the difference between a screen and a wait.
        """
        wanted = [i for i in set(ids) if i]
        if not wanted:
            return []
        return list(
            self.session.scalars(self._base().where(self.model.id.in_(wanted))).all()
        )

    def list(self, *, limit: int = DEFAULT_LIMIT, offset: int = 0, **criteria: Any) -> list[R]:
        stmt = self._base()
        for column, value in criteria.items():
            stmt = stmt.where(getattr(self.model, column) == value)
        bounded = max(1, min(limit, MAX_LIMIT))
        return list(self.session.scalars(stmt.limit(bounded).offset(offset)).all())

    def count(self, **criteria: Any) -> int:
        from sqlalchemy import func

        stmt = select(func.count()).select_from(self.model).where(self.model.deleted_at.is_(None))
        for column, value in criteria.items():
            stmt = stmt.where(getattr(self.model, column) == value)
        return int(self.session.scalar(stmt) or 0)

    # -- writing ----------------------------------------------------------

    def add(self, row: R) -> R:
        self.session.add(row)
        return row

    def create(self, **fields: Any) -> R:
        """Build and stage a row.

        Exists so a use case can create a record without importing an ORM class
        -- the mapping between application concepts and storage stays inside
        this layer.
        """
        row = self.model(**fields)
        self.session.add(row)
        return row

    def save(self, row: R) -> R:
        row.version += 1
        self.session.add(row)
        return row

    def flush(self) -> None:
        """Make pending writes visible to later statements in this transaction.

        Not a commit -- the unit of work still owns that. Needed wherever a row
        must exist before something references it, such as a booking before the
        seats that point at it.
        """
        self.session.flush()

    def insert_unless(self, row: R, *, constraint: str) -> bool:
        """Insert ``row`` unless ``constraint`` refuses it; False when it does.

        For a rule the database already enforces with a unique constraint or
        index. Checking first and then inserting is two steps, and two
        requests can both pass the check; the constraint is the guarantee,
        and this turns its refusal into an answer instead of a 500. The
        insert runs in a savepoint, so the refusal leaves the rest of the
        transaction usable -- the caller can read the row that won and say
        which one it was. A violation of any other constraint is not this
        rule's business and is raised as it was.
        """
        try:
            with self.session.begin_nested():
                self.session.add(row)
        except IntegrityError as exc:
            if violated_constraint(exc) != constraint:
                raise
            return False
        return True

    def advisory_lock(self, key: str) -> None:
        """Serialise every holder of ``key`` until this transaction ends.

        For a rule about rows that do not exist yet -- a count followed by an
        insert -- where there is no row to hold FOR UPDATE. Released by the
        commit or rollback that ends the transaction, so it cannot leak.
        """
        self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": key}
        )

    def soft_delete(self, row: R, *, at: Any, by: str | None = None) -> None:
        """Hard deletion exists only in a documented purge job."""
        row.deleted_at = at
        row.updated_by = by
        row.version += 1
        self.session.add(row)


def violated_constraint(exc: IntegrityError) -> str | None:
    """The name of the constraint or unique index PostgreSQL refused on."""
    diag = getattr(getattr(exc, "orig", None), "diag", None)
    return getattr(diag, "constraint_name", None)
