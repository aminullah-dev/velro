"""Wire schemas.

Never reused as domain entities and never as ORM models. Three shapes, three
purposes: wire (these), business (domain dataclasses), storage (ORM rows).

JSON is snake_case, matching the database and the Python code, so a field name
never has to be translated in three places. Money is always an object, never a
decimal string and never a float.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class MoneyOut(Schema):
    amount_minor: int
    currency: str

    @classmethod
    def of(cls, money: Any) -> MoneyOut | None:
        if money is None:
            return None
        return cls(amount_minor=money.amount_minor, currency=money.currency)


class Envelope(BaseModel, Generic[T]):
    """The success envelope of section 65."""

    success: bool = True
    data: T | None = None
    message: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class Page(Schema, Generic[T]):
    items: list[T]
    next_cursor: str | None = None


class PageParams(Schema):
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class TimestampedOut(Schema):
    created_at: datetime
    updated_at: datetime
