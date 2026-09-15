"""Close departures whose time has passed with nobody driving and nobody booked.

Nothing in the product closes such a trip by itself yet -- whether a missed
departure should expire on its own, be re-dispatched or be cancelled with
a message is still the owner's call -- and the console has no "cancel trip"
button. Meanwhile a seeded or abandoned departure sits under "Overdue trips"
for ever, and a card that never empties is a card nobody reads.

So this closes exactly the trips it is named, and only those that are still
empty: SCHEDULED or REQUESTED, no driver, departure more than an hour gone,
and no booking that is not already cancelled. Anything else is reported and
left alone. EXPIRED, not CANCELLED: nobody called these off, their time
simply went, and CANCELLED would read as a decision somebody took.

Dry run unless --apply. Every change is written to the audit log.

    docker compose exec -T api python - VLR-2026-000001 --apply < expire-empty-trips.py
    PYTHONPATH=. .venv/bin/python scripts/expire-empty-trips.py VLR-2026-000001   # local, dry run
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import timedelta

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from domain.enums import ActorRole, BookingStatus, TripStatus
from infrastructure.db.models.trips import BookingRow, TripRow
from infrastructure.services.audit import SqlAuditLog
from shared.clock import SystemClock

#: A departure this recent may still be moving; leave it to the office.
GRACE = timedelta(hours=1)
STILL_OPEN = (TripStatus.SCHEDULED.value, TripStatus.REQUESTED.value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("numbers", nargs="+", help="trip numbers, e.g. VLR-2026-000001")
    parser.add_argument("--apply", action="store_true", help="make the change (default: show it)")
    args = parser.parse_args()

    url = os.environ.get(
        "VELRO_DATABASE_URL",
        "postgresql+psycopg://aminullahhashemi@localhost:5432/velro_dev",
    )
    clock = SystemClock()
    now = clock.now()
    closed = 0
    with Session(create_engine(url)) as session:
        audit = SqlAuditLog(session, clock)
        for number in args.numbers:
            trip = session.scalars(
                select(TripRow).where(TripRow.number == number, TripRow.deleted_at.is_(None))
            ).first()
            if trip is None:
                print(f"{number}: not found -- left alone")
                continue
            booked = int(session.scalar(
                select(func.count()).select_from(BookingRow).where(
                    BookingRow.trip_id == trip.id,
                    BookingRow.deleted_at.is_(None),
                    BookingRow.status != BookingStatus.CANCELLED.value,
                )
            ) or 0)
            why_not = (
                f"status {trip.status}" if trip.status not in STILL_OPEN
                else "has a driver" if trip.driver_id is not None
                else "departure not yet an hour gone"
                if trip.scheduled_departure_at > now - GRACE
                else f"{booked} booking(s)" if booked
                else None
            )
            if why_not:
                print(f"{number}: {why_not} -- left alone")
                continue
            departed = f"{trip.scheduled_departure_at:%Y-%m-%d %H:%M} UTC"
            print(f"{number}: {trip.status} -> EXPIRED (departed {departed})")
            if not args.apply:
                continue
            before = trip.status
            trip.status = TripStatus.EXPIRED.value
            trip.version += 1
            audit.write(
                "trip.expired",
                actor_id=None,
                actor_role=ActorRole.SYSTEM,
                entity_type="trip",
                entity_id=trip.id,
                before={"status": before},
                after={
                    "status": trip.status,
                    "reason": "departure passed with no driver and no booking; "
                              "closed by the office",
                },
            )
            closed += 1
        if args.apply:
            session.commit()
            print(f"closed {closed}")
        else:
            print("dry run: nothing changed; --apply closes the trips marked above.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
