"""What deleting an account actually touches, table by table.

The policy -- who may delete, and when not -- is DeleteAccount's. This is the
mechanics: every column in the schema that holds something about a person, and
what becomes of it when that person leaves. Kept in one place so that the day
a table grows a column with somebody's name in it, there is exactly one file
where forgetting it would show.

Three verbs, chosen per table rather than per habit:

  * **scrub** -- the row stays because other people's records point at it (a
    trip the driver drove, a booking the fare accounting counts), but the
    columns that identify or describe the person are emptied.
  * **delete** -- the row is only about reaching this person (a sign-in code,
    a push address, where his car is right now), so it goes. ADR 0005 already
    hard-deletes a dead push token for the same reason: an address is not
    history.
  * **keep** -- trips, bookings, fares, commission, settlements and safety
    reports. They are what the privacy page promises to keep, without the name.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from domain.enums import (
    DriverApprovalStatus,
    DriverAvailability,
    FareOfferStatus,
    RideRequestStatus,
    UserStatus,
    VehicleStatus,
)
from infrastructure.db.models.identity import OtpChallengeRow, UserRoleRow, UserRow
from infrastructure.db.models.ops import (
    AuditLogRow,
    CancellationRow,
    DeviceTokenRow,
    NotificationRow,
    RatingRow,
)
from infrastructure.db.models.supply import (
    DriverDocumentRow,
    DriverLocationRow,
    DriverRow,
    VehicleDocumentRow,
    VehicleRow,
)
from infrastructure.db.models.trips import (
    BookingRow,
    DispatchOfferRow,
    FareOfferRow,
    RideRequestRow,
)

#: What the office sees beside a driver whose account is gone. A code, like
#: every other reason in this column, not a sentence in one language.
ACCOUNT_DELETED_REASON = "ACCOUNT_DELETED"


@dataclass(slots=True)
class Erasure:
    """What was done, in numbers, for the audit entry; and the files to unlink."""

    counts: dict[str, int] = field(default_factory=dict)
    #: Storage keys of photographs nobody may see again: the tazkira, the
    #: licence, the selfie, the car's permit. Unlinked by the caller after the
    #: transaction commits -- never before, or a failed commit would leave a
    #: live account pointing at files that are gone.
    file_keys: list[str] = field(default_factory=list)


class AccountEraser:
    def __init__(self, session: Session) -> None:
        self.session = session

    def erase(self, user_id: str, *, driver_id: str | None, at: datetime) -> Erasure:
        out = Erasure()
        user = self.session.scalars(
            select(UserRow).where(UserRow.id == user_id).with_for_update()
        ).one()
        phone = user.phone

        self._close_open_requests(user_id, at=at, out=out)
        self._scrub_passenger_words(user_id, out=out)
        if driver_id is not None:
            self._retire_driver(driver_id, at=at, out=out)

        # Reaching this person: gone.
        out.counts["push_tokens"] = self._rowcount(
            delete(DeviceTokenRow).where(DeviceTokenRow.user_id == user_id)
        )
        if phone:
            # Sign-in codes are hashed, but the row beside the hash carries the
            # number in the clear and the address it was asked from.
            out.counts["sign_in_codes"] = self._rowcount(
                delete(OtpChallengeRow).where(OtpChallengeRow.phone == phone)
            )
        out.counts["notifications"] = self._rowcount(
            update(NotificationRow)
            .where(NotificationRow.user_id == user_id, NotificationRow.deleted_at.is_(None))
            .values(payload={}, failure_reason=None, deleted_at=at)
        )
        # No keys left on the tombstone. A role held by nobody is the one kind
        # of access nobody thinks to revoke later.
        out.counts["roles"] = self._rowcount(
            update(UserRoleRow)
            .where(UserRoleRow.user_id == user_id, UserRoleRow.deleted_at.is_(None))
            .values(deleted_at=at)
        )

        # The audit trail keeps what happened and drops who it happened to:
        # RecordName wrote the name itself into before/after, and every entry
        # he caused carries the address he sent it from.
        self._rowcount(
            update(AuditLogRow)
            .where(
                AuditLogRow.entity_type == "user",
                AuditLogRow.entity_id == user_id,
                AuditLogRow.action == "user.name_recorded",
            )
            .values(before=None, after=None)
        )
        self._rowcount(
            update(AuditLogRow)
            .where(AuditLogRow.actor_id == user_id, AuditLogRow.ip_address.is_not(None))
            .values(ip_address=None)
        )

        if user.photo_key:
            out.file_keys.append(user.photo_key)
        # The row stays: bookings, trips, ratings and commission point at it.
        # deleted_at stays empty for the same reason -- every read of an old
        # receipt goes through a repository that filters on it, and a receipt
        # that 404s because the other party left is a broken receipt.
        # DEACTIVATED is the switch that refuses the tokens; a NULL phone is
        # what lets the same SIM start again.
        user.phone = None
        user.full_name = None
        user.email = None
        user.photo_key = None
        user.last_seen_at = None
        user.status = UserStatus.DEACTIVATED.value
        user.updated_by = user_id
        user.version += 1
        self.session.add(user)
        self.session.flush()
        return out

    # -- the passenger's side -------------------------------------------

    def _close_open_requests(self, user_id: str, *, at: datetime, out: Erasure) -> None:
        """A request still in the air is withdrawn, and the drivers who bid on
        it are told, exactly as if she had tapped cancel."""
        open_ids = list(
            self.session.scalars(
                select(RideRequestRow.id).where(
                    RideRequestRow.passenger_id == user_id,
                    RideRequestRow.status == RideRequestStatus.OPEN.value,
                    RideRequestRow.deleted_at.is_(None),
                )
            ).all()
        )
        if not open_ids:
            out.counts["requests_closed"] = 0
            return
        out.counts["requests_closed"] = self._rowcount(
            update(RideRequestRow)
            .where(RideRequestRow.id.in_(open_ids))
            .values(
                status=RideRequestStatus.CANCELLED.value,
                version=RideRequestRow.version + 1,
            )
        )
        self._rowcount(
            update(FareOfferRow)
            .where(
                FareOfferRow.ride_request_id.in_(open_ids),
                FareOfferRow.status == FareOfferStatus.OFFERED.value,
            )
            .values(
                status=FareOfferStatus.DECLINED.value,
                responded_at=at,
                version=FareOfferRow.version + 1,
            )
        )

    def _scrub_passenger_words(self, user_id: str, *, out: Erasure) -> None:
        """Free text she typed. The fare accounting needs the booking; it has
        never needed what she wrote to the driver on it."""
        out.counts["notes"] = (
            self._rowcount(
                update(BookingRow)
                .where(BookingRow.passenger_id == user_id, BookingRow.passenger_note.is_not(None))
                .values(passenger_note=None)
            )
            + self._rowcount(
                update(RideRequestRow)
                .where(RideRequestRow.passenger_id == user_id, RideRequestRow.note.is_not(None))
                .values(note=None)
            )
            + self._rowcount(
                update(CancellationRow)
                .where(
                    CancellationRow.cancelled_by_user_id == user_id,
                    CancellationRow.note.is_not(None),
                )
                .values(note=None)
            )
        )
        # The score stays -- it is the other person's average -- and the words
        # beside it go.
        out.counts["rating_comments"] = self._rowcount(
            update(RatingRow)
            .where(RatingRow.rater_user_id == user_id, RatingRow.comment.is_not(None))
            .values(comment=None)
        )

    # -- the driver's side -----------------------------------------------

    def _retire_driver(self, driver_id: str, *, at: datetime, out: Erasure) -> None:
        # Bids still on the board are taken back, or a passenger could accept
        # an offer from a man who is no longer there.
        out.counts["offers_withdrawn"] = self._rowcount(
            update(FareOfferRow)
            .where(
                FareOfferRow.driver_id == driver_id,
                FareOfferRow.status == FareOfferStatus.OFFERED.value,
            )
            .values(
                status=FareOfferStatus.WITHDRAWN.value,
                responded_at=at,
                version=FareOfferRow.version + 1,
            )
        )
        # And a trip the office offered him and he never answered is answered
        # now, so dispatch moves on to the next man instead of waiting out the
        # timer on somebody who has left.
        self._rowcount(
            update(DispatchOfferRow)
            .where(
                DispatchOfferRow.driver_id == driver_id,
                DispatchOfferRow.responded_at.is_(None),
            )
            .values(responded_at=at, response="DECLINED", decline_reason=ACCOUNT_DELETED_REASON)
        )
        # One row, where his car is now. Nothing to keep.
        self._rowcount(delete(DriverLocationRow).where(DriverLocationRow.driver_id == driver_id))

        documents = list(
            self.session.scalars(
                select(DriverDocumentRow).where(
                    DriverDocumentRow.driver_id == driver_id,
                    DriverDocumentRow.deleted_at.is_(None),
                )
            ).all()
        )
        vehicle_ids = list(
            self.session.scalars(
                select(VehicleRow.id).where(
                    VehicleRow.driver_id == driver_id, VehicleRow.deleted_at.is_(None)
                )
            ).all()
        )
        permits = (
            list(
                self.session.scalars(
                    select(VehicleDocumentRow).where(
                        VehicleDocumentRow.vehicle_id.in_(vehicle_ids),
                        VehicleDocumentRow.deleted_at.is_(None),
                    )
                ).all()
            )
            if vehicle_ids
            else []
        )
        for row in [*documents, *permits]:
            if row.file_key:
                out.file_keys.append(row.file_key)
            row.file_key = ""
            row.rejection_reason = None
            row.deleted_at = at
            row.version += 1
            self.session.add(row)
        out.counts["documents"] = len(documents) + len(permits)

        # The car stays on the trips it drove -- a passenger's old receipt
        # still names the plate she rode behind -- but it can never be
        # dispatched again.
        out.counts["vehicles_retired"] = (
            self._rowcount(
                update(VehicleRow)
                .where(VehicleRow.id.in_(vehicle_ids))
                .values(status=VehicleStatus.RETIRED.value, version=VehicleRow.version + 1)
            )
            if vehicle_ids
            else 0
        )

        # Suspended with a reason the office can read, not deleted: his trips,
        # ratings, wallet and settlements hang off this row, and the commission
        # he owes does not stop being owed because the app was removed.
        driver = self.session.get(DriverRow, driver_id)
        if driver is not None:
            driver.availability = DriverAvailability.OFFLINE.value
            driver.approval_status = DriverApprovalStatus.SUSPENDED.value
            driver.suspended_reason = ACCOUNT_DELETED_REASON
            driver.version += 1
            self.session.add(driver)

    def _rowcount(self, statement) -> int:
        return int(self.session.execute(statement).rowcount or 0)
