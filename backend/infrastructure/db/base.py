"""The ORM foundation.

Every table in VELRO carries the same seven columns -- id, created_at,
updated_at, deleted_at, created_by, updated_by, version -- with no exceptions,
including join tables. They are declared once here so no future table can
forget them.

The schema is written to the intersection of PostgreSQL and SQLite so the same
migrations serve a server deployment and an embedded one. That constrains a few
choices (text ids rather than native UUID, text enums rather than PG ENUM) and
is worth it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Integer, MetaData, String, event
from sqlalchemy.engine import Connection
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Explicit naming so Alembic autogenerate produces stable, reviewable names and
# a constraint can be dropped by name in a later migration.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    type_annotation_map = {  # noqa: RUF012
        datetime: DateTime(timezone=True),
    }


def utcnow() -> datetime:
    """Only for column defaults. Business logic uses the injected Clock."""
    return datetime.now(UTC)


class Auditable:
    """The seven mandatory columns."""

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, index=True
    )
    created_by: Mapped[str | None] = mapped_column(String(36), default=None)
    updated_by: Mapped[str | None] = mapped_column(String(36), default=None)
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


def enum_check(column: str, values: type, *, name: str) -> CheckConstraint:
    """Enumerated values are text with a CHECK, never integers.

    An integer status column is unreadable in a support session and cannot be
    safely reordered once shipped.
    """
    allowed = ", ".join(f"'{member.value}'" for member in values)  # type: ignore[attr-defined]
    return CheckConstraint(f"{column} IN ({allowed})", name=name)


@event.listens_for(Base.metadata, "after_create")
def _enable_sqlite_foreign_keys(target: Any, connection: Connection, **kw: Any) -> None:
    """SQLite ignores foreign keys unless the pragma is on for every connection.

    A schema whose constraints are silently unenforced is worse than one with
    none, because it is trusted.
    """
    if connection.dialect.name == "sqlite":
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
