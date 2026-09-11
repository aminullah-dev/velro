"""Deleting your own account, from inside the app.

The App Store will not list an app that lets somebody open an account and
gives them no way to close it from the same place; neither will Google. And
the privacy page has promised since the day it went up that an account can be
deleted -- by writing to us. This is the tap that replaces the letter.

What "deleted" means is the privacy page's sentence, made exact: everything
that says who you are or how to reach you goes; the trips and the money that
changed hands stay, without your name, because a driver's commission and a
passenger's receipt do not stop being true when one of them leaves. The
table-by-table list lives in AccountEraser.

Three refusals, each one something the person can do something about:

  * a seat is booked for you -- cancel it or ride it first, or a driver is
    driving to a station for somebody who no longer exists;
  * you are driving a trip -- finish it first, or the passengers in your car
    lose the only person who knows where they are;
  * the account opens the office -- another administrator closes it, for the
    same reason an administrator cannot suspend himself: one tap from inside
    must not lock the whole office out.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from application.ports.repositories import (
    BookingRepository,
    DriverRepository,
    RefreshTokenRepository,
    TripRepository,
    UserRepository,
)
from application.ports.services import AuditLog
from domain.enums import ActorRole
from domain.identity import STAFF_ROLES
from shared import error_codes
from shared.clock import Clock
from shared.errors import ConflictError
from shared.errors import PermissionError as DomainPermissionError


class Eraser(Protocol):
    def erase(self, user_id: str, *, driver_id: str | None, at: Any) -> Any: ...


@dataclass(frozen=True, slots=True)
class DeleteAccountCommand:
    user_id: str
    actor_role: ActorRole


@dataclass(frozen=True, slots=True)
class DeleteAccountResult:
    #: Photographs to unlink once the transaction has committed.
    file_keys: list[str]


class DeleteAccount:
    def __init__(
        self,
        *,
        users: UserRepository,
        bookings: BookingRepository,
        drivers: DriverRepository,
        trips: TripRepository,
        refresh_tokens: RefreshTokenRepository,
        eraser: Eraser,
        audit: AuditLog,
        clock: Clock,
    ) -> None:
        self._users = users
        self._bookings = bookings
        self._drivers = drivers
        self._trips = trips
        self._refresh = refresh_tokens
        self._eraser = eraser
        self._audit = audit
        self._clock = clock

    def execute(self, cmd: DeleteAccountCommand) -> DeleteAccountResult:
        now = self._clock.now()
        roles = set(self._users.roles_of(cmd.user_id))
        if roles & STAFF_ROLES:
            raise DomainPermissionError(
                error_codes.ACCOUNT_STAFF_UNDELETABLE, user_id=cmd.user_id
            )

        active = self._bookings.count_active_for_passenger(cmd.user_id)
        if active:
            raise ConflictError(
                error_codes.ACCOUNT_HAS_ACTIVE_BOOKING, user_id=cmd.user_id, bookings=active
            )

        driver = self._drivers.find_by_user(cmd.user_id)
        if driver is not None:
            in_flight = self._trips.active_for_driver(driver.id)
            if in_flight is not None:
                raise ConflictError(
                    error_codes.ACCOUNT_HAS_ACTIVE_TRIP,
                    user_id=cmd.user_id, trip_id=in_flight.id,
                )

        erasure = self._eraser.erase(
            cmd.user_id, driver_id=driver.id if driver is not None else None, at=now
        )
        # Every phone signed in to this account is signed out on its next
        # request: the refresh tokens are revoked here, and the access tokens
        # meet a DEACTIVATED row in current_actor.
        revoked = self._refresh.revoke_all_for_user(cmd.user_id, at=now)

        # Numbers only. An audit entry that recorded what was deleted would be
        # the one copy of it left.
        self._audit.write(
            "user.deleted_by_owner",
            actor_id=cmd.user_id,
            actor_role=cmd.actor_role,
            entity_type="user",
            entity_id=cmd.user_id,
            after={
                **erasure.counts,
                "sessions_revoked": revoked,
                "files": len(erasure.file_keys),
                "was_driver": driver is not None,
            },
        )
        return DeleteAccountResult(file_keys=list(erasure.file_keys))
