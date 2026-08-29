"""Business-number allocation.

The only identifier a user ever sees. A row id never appears in a URL or on a
printed document; ``BKG-2026-000042`` does.

Gap-free within a year, so the sequence is a locked row rather than a
PostgreSQL SEQUENCE -- a sequence does not roll back, and a rolled-back booking
would leave a hole that an auditor will ask about.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from infrastructure.db.models.ops import NumberSequenceRow
from shared.ids import new_id

# entity -> (prefix, padding)
_FORMATS: dict[str, tuple[str, int]] = {
    "trip": ("VLR", 6),
    "booking": ("BKG", 6),
    "settlement": ("STL", 6),
    "ticket": ("TKT", 6),
}


class SqlNumberAllocator:
    def __init__(self, session: Session) -> None:
        self._session = session

    def allocate(self, entity: str, *, year: int) -> str:
        prefix, padding = _FORMATS.get(entity, (entity[:3].upper(), 6))

        row = self._session.scalars(
            select(NumberSequenceRow)
            .where(
                NumberSequenceRow.entity == entity,
                NumberSequenceRow.year == year,
                NumberSequenceRow.deleted_at.is_(None),
            )
            .with_for_update()          # serialise allocation; the hold is microseconds
        ).one_or_none()

        if row is None:
            row = NumberSequenceRow(
                id=new_id(), entity=entity, year=year, next_value=1,
                prefix=prefix, padding=padding,
            )
            self._session.add(row)
            self._session.flush()
            # Re-read under lock: two transactions may both have found nothing.
            # The unique constraint on (entity, year) means only one insert wins,
            # and the loser's flush raises rather than creating a second sequence.

        value = row.next_value
        row.next_value = value + 1
        row.version += 1
        self._session.add(row)
        return f"{row.prefix}-{year}-{value:0{row.padding}d}"
