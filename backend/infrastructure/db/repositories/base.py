"""Repository base.

Two things happen here so that no individual query can forget them:
soft-delete filtering, and a bounded default limit. A repository method that
returns an unbounded list is a production incident waiting for the table to
grow.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from sqlalchemy import Select, select
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

    def find_by(self, **criteria: Any) -> R | None:
        stmt = self._base()
        for column, value in criteria.items():
            stmt = stmt.where(getattr(self.model, column) == value)
        return self.session.scalars(stmt).first()

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

    def soft_delete(self, row: R, *, at: Any, by: str | None = None) -> None:
        """Hard deletion exists only in a documented purge job."""
        row.deleted_at = at
        row.updated_by = by
        row.version += 1
        self.session.add(row)
