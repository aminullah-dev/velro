"""A passenger says what the place they are standing in is called.

This is how VELRO learns the villages its map has never placed: the passenger
who taps "my current location" is asked the name of the place, and the answer
is kept for the next person standing there (ADR 0015).

Three decisions are made here and nowhere else:

- **Is it a place name at all.** `domain.places` refuses households, people,
  phone numbers and bare words like "مسجد" before anything is stored.
- **Which district.** Inferred from the fix, never typed -- the passenger is
  not asked a question the phone already knows the answer to. They may
  correct it, because the inference is the nearest station's district and a
  valley's edge can fool it.
- **Who may see it.** A name that is a known village or alias in that
  district, typed near where that village is, is approved at once. Anything
  else waits PENDING until staff read it: shown to nobody but the driver of
  the one request it came with, which is no more than the free-text note
  already is.

Anonymous by construction. The row has no user column, `created_by` is left
empty, and nothing is written to the audit log -- an audit entry naming the
passenger beside a coordinate would be the very trail the privacy page says
VELRO does not keep.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from domain.enums import PlaceStatus
from domain.geography import approx_distance_m
from domain.places import assert_allowed, place_key
from shared import error_codes
from shared.clock import Clock
from shared.errors import NotFoundError, ValidationError

#: Two reports of one name this close together are one place. A village is
#: wider than this; two villages of the same name in one district are not
#: this close.
SAME_PLACE_WITHIN_M = 1_500

#: A name that matches a known village is approved only when it is typed
#: within this distance of where that village is known to be. Further than
#: this, "قلعه نو" is either a second place of the same name or a mistake,
#: and a person decides which.
VILLAGE_MATCH_WITHIN_M = 6_000

#: How far a fix may be from any station and still infer a district.
DISTRICT_REACH_M = 20_000


@dataclass(frozen=True, slots=True)
class ReportPlaceCommand:
    name: str | None
    latitude: Decimal
    longitude: Decimal
    #: Only when the passenger corrected the inferred district.
    district_id: str | None = None


class ReportPlace:
    def __init__(self, *, geography, clock: Clock, new_id: Callable[[], str]) -> None:
        self._geo = geography
        self._clock = clock
        self._new_id = new_id

    def execute(self, cmd: ReportPlaceCommand):
        name = assert_allowed(cmd.name)
        key = place_key(name)
        now = self._clock.now()

        inferred = self._geo.nearest_district(
            cmd.latitude, cmd.longitude, radius_m=DISTRICT_REACH_M
        )
        if cmd.district_id is not None:
            district_id = cmd.district_id
            if not any(d.id == district_id for d in self._geo.list_districts()):
                raise NotFoundError(error_codes.DISTRICT_NOT_FOUND, district_id=district_id)
        elif inferred is not None:
            district_id = inferred[0].id
        else:
            # The router's geofence normally stops this first; an exempt test
            # number standing in another country arrives here instead.
            raise ValidationError(
                error_codes.GEOFENCE_OUTSIDE,
                latitude=str(cmd.latitude),
                longitude=str(cmd.longitude),
            )

        existing = self._geo.same_place(
            district_id, key, cmd.latitude, cmd.longitude, within_m=SAME_PLACE_WITHIN_M
        )
        if existing is not None:
            if existing.status == PlaceStatus.REJECTED.value:
                # Staff have read this name and said no. Saying so again is
                # the honest answer; a fresh PENDING row would put the same
                # name back in front of them tomorrow.
                raise ValidationError(error_codes.PLACE_NAME_NOT_ALLOWED, reason="rejected")
            existing.report_count += 1
            existing.last_reported_at = now
            existing.version += 1
            return existing

        village = self._geo.village_named(district_id, name)
        approved = village is not None and _near_enough(village, cmd)
        nearest = self._geo.nearby_stations(
            cmd.latitude, cmd.longitude, radius_m=DISTRICT_REACH_M, limit=1
        )
        return self._geo.add_place(
            id=self._new_id(),
            name=name,
            name_key=key,
            district_id=district_id,
            village_id=village.id if village is not None else None,
            nearest_station_id=nearest[0][0].id if nearest else None,
            latitude=cmd.latitude,
            longitude=cmd.longitude,
            status=(PlaceStatus.APPROVED if approved else PlaceStatus.PENDING).value,
            report_count=1,
            last_reported_at=now,
        )


def _near_enough(village, cmd: ReportPlaceCommand) -> bool:
    """A village nobody has placed cannot be too far away -- 415 of them have
    no point yet, and their names are exactly the ones this feature exists to
    learn."""
    if village.latitude is None or village.longitude is None:
        return True
    distance = approx_distance_m(
        cmd.latitude, cmd.longitude, village.latitude, village.longitude
    )
    return distance <= VILLAGE_MATCH_WITHIN_M
