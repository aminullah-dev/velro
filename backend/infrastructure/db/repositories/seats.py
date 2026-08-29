"""Seat allocation.

This is the load-bearing query of the whole platform. Two passengers must never
both succeed in reserving the same final seat, and the guarantee has to hold
under real concurrency rather than in the happy path.

Three mechanisms, at three levels:

1. ``FOR UPDATE SKIP LOCKED`` -- rows already being considered by another
   transaction are skipped rather than waited on. This gives *liveness*: a
   second passenger booking a different seat is not blocked behind the first.
2. Re-checking ``status = 'AVAILABLE'`` inside the locked read. This gives
   *correctness at the application level*.
3. ``UNIQUE (trip_seat_id)`` on ``booking_seats``. This gives *correctness that
   survives this file being edited carelessly later*. It is the backstop, and it
   is the reason a reviewer can trust the invariant without reading this query.

The seats themselves are rows, so capacity cannot be exceeded by construction --
there is no counter to decrement wrongly.
"""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from domain.enums import SeatStatus
from infrastructure.db.models.trips import BookingSeatRow, TripSeatRow
from infrastructure.db.repositories.base import SqlRepository
from shared import error_codes
from shared.errors import ConflictError


class TripSeatRepository(SqlRepository[TripSeatRow]):
    model = TripSeatRow
    not_found_code = error_codes.TRIP_SEATS_UNAVAILABLE

    def list_for_trip(self, trip_id: str) -> list[TripSeatRow]:
        stmt = self._base().where(TripSeatRow.trip_id == trip_id).order_by(TripSeatRow.seat_number)
        return list(self.session.scalars(stmt).all())

    def count_available(self, trip_id: str) -> int:
        return self.count(trip_id=trip_id, status=SeatStatus.AVAILABLE.value)

    def lock_available(self, trip_id: str, seat_count: int) -> list[TripSeatRow]:
        """Take an exclusive lock on ``seat_count`` available seats, or raise.

        The lock is held until the surrounding transaction commits or rolls
        back, which is why this must only ever be called from inside a
        UnitOfWork that will shortly do one or the other.
        """
        if seat_count <= 0:
            raise ConflictError(
                error_codes.BOOKING_SEAT_COUNT_INVALID, trip_id=trip_id, requested=seat_count
            )

        dialect = self.session.get_bind().dialect.name

        stmt = (
            select(TripSeatRow)
            .where(
                TripSeatRow.trip_id == trip_id,
                TripSeatRow.status == SeatStatus.AVAILABLE.value,
                TripSeatRow.booking_id.is_(None),
                TripSeatRow.deleted_at.is_(None),
            )
            .order_by(TripSeatRow.seat_number)
            .limit(seat_count)
        )

        if dialect == "postgresql":
            # skip_locked: a row another transaction is already holding is not
            # ours to take, and waiting for it would only serialise every
            # booking on the trip behind the slowest one.
            stmt = stmt.with_for_update(skip_locked=True)
        elif dialect != "sqlite":
            stmt = stmt.with_for_update()
        # SQLite has no row locks; its whole-database write lock plus the unique
        # constraint below provide the same guarantee for the embedded case.

        seats = list(self.session.scalars(stmt).all())

        if len(seats) < seat_count:
            # Report what is genuinely left, not what we failed to lock: the
            # number the passenger sees should match the number they can book.
            raise ConflictError(
                error_codes.TRIP_SEATS_UNAVAILABLE,
                trip_id=trip_id,
                requested=seat_count,
                available=self.count_available(trip_id),
            )
        return seats

    def reserve(self, seats: list[TripSeatRow], booking_id: str) -> list[BookingSeatRow]:
        """Mark locked seats as reserved and bind them to the booking.

        The ``status = AVAILABLE`` predicate is repeated in the UPDATE so that
        even a caller who skipped ``lock_available`` cannot overwrite a seat
        that someone else already took.
        """
        links: list[BookingSeatRow] = []
        for seat in seats:
            result = self.session.execute(
                update(TripSeatRow)
                .where(
                    TripSeatRow.id == seat.id,
                    TripSeatRow.status == SeatStatus.AVAILABLE.value,
                    TripSeatRow.booking_id.is_(None),
                )
                .values(
                    status=SeatStatus.RESERVED.value,
                    booking_id=booking_id,
                    version=TripSeatRow.version + 1,
                )
            )
            if result.rowcount != 1:
                raise ConflictError(
                    error_codes.TRIP_SEATS_UNAVAILABLE,
                    trip_id=seat.trip_id,
                    seat_number=seat.seat_number,
                    reason="seat_taken_concurrently",
                )
            links.append(
                BookingSeatRow(
                    id=_link_id(booking_id, seat.id),
                    booking_id=booking_id,
                    trip_seat_id=seat.id,
                    seat_number=seat.seat_number,
                )
            )
        self.session.add_all(links)
        return links

    def release_for_booking(self, booking_id: str) -> int:
        """Return a cancelled booking's seats to the pool. Never touches BLOCKED seats."""
        result = self.session.execute(
            update(TripSeatRow)
            .where(
                TripSeatRow.booking_id == booking_id,
                TripSeatRow.status.in_(
                    (SeatStatus.RESERVED.value, SeatStatus.OCCUPIED.value)
                ),
            )
            .values(
                status=SeatStatus.AVAILABLE.value,
                booking_id=None,
                version=TripSeatRow.version + 1,
            )
        )
        self.session.execute(
            BookingSeatRow.__table__.delete().where(BookingSeatRow.booking_id == booking_id)
        )
        return int(result.rowcount or 0)

    def occupy_for_booking(self, booking_id: str) -> int:
        result = self.session.execute(
            update(TripSeatRow)
            .where(
                TripSeatRow.booking_id == booking_id,
                TripSeatRow.status == SeatStatus.RESERVED.value,
            )
            .values(status=SeatStatus.OCCUPIED.value, version=TripSeatRow.version + 1)
        )
        return int(result.rowcount or 0)


def _link_id(booking_id: str, seat_id: str) -> str:
    """Deterministic id for the join row.

    A retry of the same booking therefore collides on the primary key as well as
    on the unique constraint, which makes a duplicated request fail loudly
    instead of quietly creating a second link.
    """
    import hashlib

    digest = hashlib.sha256(f"{booking_id}:{seat_id}".encode()).hexdigest()
    return f"{digest[0:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"


def open_session_repository(session: Session) -> TripSeatRepository:
    return TripSeatRepository(session)
