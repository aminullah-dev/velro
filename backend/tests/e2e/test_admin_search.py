"""Finding one thing in the staff console's lists.

A driver's complaint arrives as a phone number read out over the line, typed
on whatever keyboard the operator has open. A passenger quotes the number on
her receipt. An administrator asks what one colleague did last week. Each is
a question about one row, and until now each meant scrolling a list that
stopped at two hundred.

Everything here is additive: the same lists, the same gates, the same shapes,
with a filter or a field more -- so the web panel and the handsets already in
the valley keep working unchanged.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from domain.text import to_eastern_digits
from tests.e2e.conftest import auth, sign_in

pytestmark = pytest.mark.integration

#: A driver with a Latin name and a plate typed on a Persian keyboard.
OWNER = "+93700000870"
#: A dispatcher: staff, not an administrator.
DESK = "+93700000871"
#: A passenger, who may search none of this.
RIDER = "+93700000872"

NAME = "Rahim Gul"
PLATE = "SRC ۸۷۰۱"            # stored as typed; its key is SRC8701

USERS = "/api/v1/admin/users"
DRIVERS = "/api/v1/admin/drivers"
VEHICLES = "/api/v1/admin/vehicles"
TRIPS = "/api/v1/admin/trips"
BOOKINGS = "/api/v1/admin/bookings"
AUDIT = "/api/v1/admin/audit"

NOBODY = "00000000-0000-0000-0000-000000000000"


def _session():
    from ui.api import deps

    return deps._session_factory()()


def _get(client: TestClient, path: str, headers: dict, **params) -> dict:
    answer = client.get(path, headers=headers, params=params)
    assert answer.status_code == 200, answer.text
    return answer.json()


def _ids(body: dict) -> set[str]:
    return {row["id"] for row in body["data"]}


# -- the people and things being looked for --------------------------------


@pytest.fixture(scope="module")
def owner(client: TestClient) -> dict:
    """A driver who has registered and is waiting for approval, with a car.

    The car is written directly rather than through the driver's app: what is
    under test is finding it, not registering it, and the registration rules
    have their own module.
    """
    from domain.driver import normalise_plate
    from infrastructure.db.models.identity import UserRow
    from infrastructure.db.models.supply import DriverRow, VehicleRow
    from shared.ids import new_id

    headers = auth(sign_in(client, OWNER))
    registered = client.post("/api/v1/driver/register", json={}, headers=headers)
    assert registered.status_code in (200, 201), registered.text

    with _session() as session:
        user = session.scalars(select(UserRow).where(UserRow.phone == OWNER)).one()
        user.full_name = NAME
        driver = session.scalars(
            select(DriverRow).where(DriverRow.user_id == user.id)
        ).one()
        vehicle = VehicleRow(
            id=new_id(), driver_id=driver.id, vehicle_type_code="SEDAN",
            plate_number=PLATE, plate_key=normalise_plate(PLATE), seat_capacity=4,
        )
        session.add(vehicle)
        found = {"driver_id": driver.id, "vehicle_id": vehicle.id, "user_id": user.id}
        session.commit()
    return found


@pytest.fixture(scope="module")
def desk(client: TestClient) -> dict:
    """Open an account the ordinary way, then give it a dispatcher's desk."""
    from infrastructure.db.models.identity import UserRow
    from infrastructure.db.repositories.identity import UserRepository

    headers = auth(sign_in(client, DESK))
    with _session() as session:
        user = session.scalars(select(UserRow).where(UserRow.phone == DESK)).one()
        UserRepository(session).grant_role(user.id, "DISPATCHER")
        user_id = user.id
        session.commit()
    return {"headers": headers, "user_id": user_id}


@pytest.fixture(scope="module")
def rider(client: TestClient) -> dict:
    return auth(sign_in(client, RIDER))


@pytest.fixture(scope="module")
def booked(client: TestClient, rider: dict) -> dict:
    """A trip that belongs to this module alone, with one seat booked on it.

    The seeded trips are shared, and other modules assert on their exact seat
    counts; a trip published here is answerable to nobody else.
    """
    from domain.enums import RideKind, TripStatus
    from infrastructure.db.models.routing import RouteRow, RouteStopRow
    from infrastructure.db.models.trips import TripRow, TripSeatRow, TripStopRow
    from infrastructure.services.numbers import SqlNumberAllocator
    from shared.clock import SystemClock
    from shared.ids import new_id

    with _session() as session:
        route = session.scalars(
            select(RouteRow).where(RouteRow.deleted_at.is_(None)).limit(1)
        ).one()
        stops = list(
            session.scalars(
                select(RouteStopRow)
                .where(RouteStopRow.route_id == route.id)
                .order_by(RouteStopRow.sequence)
            ).all()
        )
        departure = SystemClock().now() + timedelta(hours=6)
        trip = TripRow(
            id=new_id(),
            number=SqlNumberAllocator(session).allocate("trip", year=departure.year),
            route_id=route.id,
            ride_kind=RideKind.SHARED.value,
            seat_capacity=4,
            scheduled_departure_at=departure,
            status=TripStatus.SCHEDULED.value,
            origin_station_id=route.origin_station_id,
            destination_id=route.destination_id,
        )
        session.add(trip)
        session.flush()
        for stop in stops:
            session.add(
                TripStopRow(
                    id=new_id(), trip_id=trip.id, sequence=stop.sequence,
                    station_id=stop.station_id, destination_id=stop.destination_id,
                    planned_at=departure + timedelta(minutes=30 * stop.sequence),
                )
            )
        for seat_number in range(1, trip.seat_capacity + 1):
            session.add(TripSeatRow(id=new_id(), trip_id=trip.id, seat_number=seat_number))
        journey = {
            "trip_id": trip.id,
            "number": trip.number,
            "station_id": route.origin_station_id,
            "destination_id": route.destination_id,
        }
        session.commit()

    made = client.post(
        "/api/v1/bookings",
        json={
            "trip_id": journey["trip_id"],
            "seat_count": 1,
            "pickup_station_id": journey["station_id"],
            "dropoff_destination_id": journey["destination_id"],
        },
        headers={**rider, "Idempotency-Key": f"admin-search-{journey['trip_id'][-8:]}"},
    )
    assert made.status_code in (200, 201), made.text
    return journey


@pytest.fixture(scope="module")
def desk_history(desk: dict) -> str:
    """Two entries in the audit log with the dispatcher's name on them.

    Written directly: the filter is the read side, and an audited action
    would change shared data that other modules read.
    """
    from infrastructure.db.models.ops import AuditLogRow
    from shared.clock import SystemClock
    from shared.ids import new_id

    now = SystemClock().now()
    with _session() as session:
        for n, action in enumerate(("test.lookup.first", "test.lookup.second")):
            session.add(
                AuditLogRow(
                    id=new_id(), occurred_at=now - timedelta(seconds=n),
                    actor_id=desk["user_id"], actor_role="DISPATCHER", action=action,
                    entity_type="user", entity_id=desk["user_id"],
                    before=None, after={"n": n}, origin="admin",
                )
            )
        session.commit()
    return desk["user_id"]


# -- drivers ---------------------------------------------------------------


class TestFindingADriver:
    @pytest.mark.parametrize("typed", [
        "0700000870",
        "+93700000870",
        "0093 700 000 870",
        "700000870",
        "۰۷۰۰۰۰۰۸۷۰",          # Persian / Pashto keyboard
        "٠٧٠٠٠٠٠٨٧٠",          # Arabic keyboard
    ])
    def test_his_phone_finds_him_however_it_was_typed(
        self, client: TestClient, admin_session: dict, owner: dict, typed: str
    ) -> None:
        body = _get(client, DRIVERS, admin_session, search=typed)
        assert owner["driver_id"] in _ids(body)
        assert all("700000870" in (d["phone"] or "") for d in body["data"])
        assert body["meta"]["total"] == len(body["data"])

    @pytest.mark.parametrize("typed", ["rahim", "RAHIM GUL", "  gul "])
    def test_his_name_finds_him_in_any_case(
        self, client: TestClient, admin_session: dict, owner: dict, typed: str
    ) -> None:
        assert owner["driver_id"] in _ids(_get(client, DRIVERS, admin_session, search=typed))

    def test_a_seeded_persian_name_is_found(
        self, client: TestClient, admin_session: dict
    ) -> None:
        body = _get(client, DRIVERS, admin_session, search="نجیب")
        assert "+93700000021" in {d["phone"] for d in body["data"]}

    def test_nobody_is_nobody(self, client: TestClient, admin_session: dict) -> None:
        body = _get(client, DRIVERS, admin_session, search="no-such-driver-xyzzy")
        assert body["data"] == []
        assert body["meta"]["total"] == 0

    def test_a_percent_sign_is_a_character_not_a_wildcard(
        self, client: TestClient, admin_session: dict, owner: dict
    ) -> None:
        assert _get(client, DRIVERS, admin_session, search="%")["meta"]["total"] == 0

    def test_a_blank_box_is_no_filter(
        self, client: TestClient, admin_session: dict, owner: dict
    ) -> None:
        blank = _get(client, DRIVERS, admin_session, search="   ", limit=200)
        everyone = _get(client, DRIVERS, admin_session, limit=200)
        assert blank["meta"]["total"] == everyone["meta"]["total"]

    def test_the_existing_filters_still_narrow(
        self, client: TestClient, admin_session: dict, owner: dict
    ) -> None:
        waiting = _get(client, DRIVERS, admin_session, approval_status="PENDING", search=OWNER)
        assert owner["driver_id"] in _ids(waiting)
        approved = _get(client, DRIVERS, admin_session, approval_status="APPROVED", search=OWNER)
        assert owner["driver_id"] not in _ids(approved)

    def test_the_list_pages_past_its_limit(
        self, client: TestClient, admin_session: dict, owner: dict
    ) -> None:
        everyone = _get(client, DRIVERS, admin_session, limit=200)
        total = everyone["meta"]["total"]
        assert total >= 3, "two seeded drivers and this module's"
        assert everyone["meta"] == {"total": total, "limit": 200, "offset": 0}
        if total <= 200:
            assert len(everyone["data"]) == total

        first = _get(client, DRIVERS, admin_session, limit=1, offset=0)
        second = _get(client, DRIVERS, admin_session, limit=1, offset=1)
        assert second["meta"] == {"total": total, "limit": 1, "offset": 1}
        # Pages stitch together: the order is total, so no row is on two pages.
        assert [first["data"][0]["id"], second["data"][0]["id"]] == [
            d["id"] for d in everyone["data"][:2]
        ]


# -- vehicles --------------------------------------------------------------


class TestFindingACar:
    @pytest.mark.parametrize("typed", ["8701", "src 8701", "SRC-۸۷۰۱", "src٨٧٠١"])
    def test_the_plate_finds_it_whichever_digits_were_typed(
        self, client: TestClient, admin_session: dict, owner: dict, typed: str
    ) -> None:
        body = _get(client, VEHICLES, admin_session, search=typed)
        assert owner["vehicle_id"] in _ids(body)
        mine = next(v for v in body["data"] if v["id"] == owner["vehicle_id"])
        assert mine["plate_number"] == PLATE, "stored as typed, never rewritten"

    @pytest.mark.parametrize("typed", ["gul", "Rahim Gul", "0700000870", "۰۷۰۰۰۰۰۸۷۰"])
    def test_its_owner_finds_it(
        self, client: TestClient, admin_session: dict, owner: dict, typed: str
    ) -> None:
        assert owner["vehicle_id"] in _ids(_get(client, VEHICLES, admin_session, search=typed))

    def test_nothing_is_nothing(self, client: TestClient, admin_session: dict) -> None:
        body = _get(client, VEHICLES, admin_session, search="no-such-plate-xyzzy")
        assert body["data"] == []
        assert body["meta"]["total"] == 0

    def test_the_list_pages_past_its_limit(
        self, client: TestClient, admin_session: dict, owner: dict
    ) -> None:
        everyone = _get(client, VEHICLES, admin_session, limit=200)
        total = everyone["meta"]["total"]
        assert total >= 3
        assert everyone["meta"] == {"total": total, "limit": 200, "offset": 0}
        second = _get(client, VEHICLES, admin_session, limit=1, offset=1)
        assert second["meta"] == {"total": total, "limit": 1, "offset": 1}
        assert second["data"][0]["id"] == everyone["data"][1]["id"]


# -- a trip by its number -------------------------------------------------


class TestATripByItsNumber:
    @pytest.mark.parametrize("variant", ["exact", "lower", "persian"])
    def test_the_number_opens_exactly_that_trip(
        self, client: TestClient, admin_session: dict, booked: dict, variant: str
    ) -> None:
        number = booked["number"]
        typed = {
            "exact": number,
            "lower": f"  {number.lower()} ",
            "persian": to_eastern_digits(number),
        }[variant]
        body = _get(client, TRIPS, admin_session, number=typed)
        assert [t["id"] for t in body["data"]] == [booked["trip_id"]]
        assert body["meta"]["total"] == 1
        trip = body["data"][0]
        assert trip["number"] == number
        assert trip["booked_seats"] == 1

    def test_an_unknown_number_is_an_empty_page_not_an_error(
        self, client: TestClient, admin_session: dict
    ) -> None:
        body = _get(client, TRIPS, admin_session, number="VLR-1999-999999")
        assert body["data"] == []
        assert body["meta"]["total"] == 0

    def test_it_is_exact_not_a_prefix(
        self, client: TestClient, admin_session: dict, booked: dict
    ) -> None:
        assert _get(client, TRIPS, admin_session, number=booked["number"][:-1])["data"] == []

    def test_it_combines_with_the_other_filters(
        self, client: TestClient, admin_session: dict, booked: dict
    ) -> None:
        found = _get(client, TRIPS, admin_session, number=booked["number"])["data"][0]
        same = _get(client, TRIPS, admin_session, number=booked["number"], status=found["status"])
        assert same["meta"]["total"] == 1
        other = "COMPLETED" if found["status"] != "COMPLETED" else "CANCELLED"
        assert _get(
            client, TRIPS, admin_session, number=booked["number"], status=other
        )["meta"]["total"] == 0


# -- a booking names its trip ---------------------------------------------


class TestABookingNamesItsTrip:
    def test_the_row_carries_the_trip_id_and_number(
        self, client: TestClient, admin_session: dict, booked: dict
    ) -> None:
        rows = _get(client, BOOKINGS, admin_session, trip_id=booked["trip_id"])["data"]
        assert len(rows) == 1
        assert rows[0]["trip_id"] == booked["trip_id"]
        assert rows[0]["trip_number"] == booked["number"]

    def test_every_row_has_one(
        self, client: TestClient, admin_session: dict, booked: dict
    ) -> None:
        rows = _get(client, BOOKINGS, admin_session, limit=200)["data"]
        assert rows
        assert all(isinstance(b["trip_id"], str) and b["trip_id"] for b in rows)


# -- the audit log by who did it -------------------------------------------


class TestTheAuditLogByWhoDidIt:
    def test_only_his_entries(
        self, client: TestClient, admin_session: dict, desk_history: str
    ) -> None:
        body = _get(client, AUDIT, admin_session, actor_id=desk_history, limit=200)
        assert body["data"]
        assert all(a["actor_id"] == desk_history for a in body["data"])
        assert {"test.lookup.first", "test.lookup.second"} <= {
            a["action"] for a in body["data"]
        }
        assert body["meta"]["total"] == len(body["data"])

    def test_it_combines_with_the_action_filter(
        self, client: TestClient, admin_session: dict, desk_history: str
    ) -> None:
        body = _get(
            client, AUDIT, admin_session, actor_id=desk_history, action="test.lookup.first"
        )
        assert [a["action"] for a in body["data"]] == ["test.lookup.first"]
        assert body["meta"] == {"total": 1, "limit": 50, "offset": 0}

    def test_an_unknown_actor_has_no_history(
        self, client: TestClient, admin_session: dict
    ) -> None:
        body = _get(client, AUDIT, admin_session, actor_id=NOBODY)
        assert body["data"] == []
        assert body["meta"]["total"] == 0


# -- a name typed on another keyboard ---------------------------------------

#: Stored with Arabic letter forms: ك kaf, ي yeh, ة teh marbuta.
ARABIC_TYPED = ("+93700000895", "كريمة علي", "FLD ۸۹۵")
#: Stored with Persian ones: ک and ی.
PERSIAN_TYPED = ("+93700000896", "زکیه یوسفی", "FLD ۸۹۶")


@pytest.fixture(scope="module")
def keyboards(client: TestClient) -> dict[str, dict]:
    """Two drivers, each with a car, whose names were typed on different
    keyboards. Written directly, like the owner above: the names are stored
    exactly as typed, and it is finding them that is under test."""
    from domain.driver import normalise_plate
    from infrastructure.db.models.identity import UserRow
    from infrastructure.db.models.supply import DriverRow, VehicleRow
    from shared.ids import new_id

    made: dict[str, dict] = {}
    for phone, name, plate in (ARABIC_TYPED, PERSIAN_TYPED):
        headers = auth(sign_in(client, phone))
        registered = client.post("/api/v1/driver/register", json={}, headers=headers)
        assert registered.status_code in (200, 201), registered.text
        with _session() as session:
            user = session.scalars(select(UserRow).where(UserRow.phone == phone)).one()
            user.full_name = name
            driver = session.scalars(
                select(DriverRow).where(DriverRow.user_id == user.id)
            ).one()
            vehicle = VehicleRow(
                id=new_id(), driver_id=driver.id, vehicle_type_code="SEDAN",
                plate_number=plate, plate_key=normalise_plate(plate), seat_capacity=4,
            )
            session.add(vehicle)
            made[phone] = {
                USERS: user.id, DRIVERS: driver.id, VEHICLES: vehicle.id, "name": name,
            }
            session.commit()
    return made


class TestANameTypedOnAnotherKeyboard:
    @pytest.mark.parametrize("path", [USERS, DRIVERS, VEHICLES])
    @pytest.mark.parametrize(("stored", "typed"), [
        # A Persian keyboard finds a name typed on an Arabic one...
        (ARABIC_TYPED, "کریمه علی"),
        (ARABIC_TYPED, "کریمه"),
        (ARABIC_TYPED, "علی"),
        # ...and an Arabic keyboard finds a name typed on a Persian one.
        (PERSIAN_TYPED, "زكيه يوسفي"),
        (PERSIAN_TYPED, "يوسفى"),          # alef maksura for the final yeh
    ])
    def test_either_keyboard_finds_it(
        self, client: TestClient, admin_session: dict, keyboards: dict,
        path: str, stored: tuple, typed: str,
    ) -> None:
        wanted = keyboards[stored[0]][path]
        assert wanted in _ids(_get(client, path, admin_session, search=typed, limit=200))

    def test_the_name_is_shown_as_it_was_typed(
        self, client: TestClient, admin_session: dict, keyboards: dict
    ) -> None:
        """Only the comparison is folded. Rewriting the name would be ours to
        do to somebody else's name, and it is not."""
        for phone, name, _ in (ARABIC_TYPED, PERSIAN_TYPED):
            users = _get(client, USERS, admin_session, search=phone)["data"]
            assert [u["full_name"] for u in users] == [name]
            drivers = _get(client, DRIVERS, admin_session, search=phone)["data"]
            assert [d["full_name"] for d in drivers] == [name]

    def test_folding_is_not_a_wildcard(
        self, client: TestClient, admin_session: dict, keyboards: dict
    ) -> None:
        found = _ids(_get(client, DRIVERS, admin_session, search="کریمه علی", limit=200))
        assert keyboards[ARABIC_TYPED[0]][DRIVERS] in found
        assert keyboards[PERSIAN_TYPED[0]][DRIVERS] not in found

    def test_a_percent_sign_is_still_a_character(
        self, client: TestClient, admin_session: dict, keyboards: dict
    ) -> None:
        assert _get(client, USERS, admin_session, search="%")["meta"]["total"] == 0
        assert _get(client, USERS, admin_session, search="كريمة_علي")["meta"]["total"] == 0


# -- the gates are the lists' own ----------------------------------------


_STAFF_LOOKUPS = [
    (DRIVERS, {"search": "0700000870"}),
    (VEHICLES, {"search": "8701"}),
    (TRIPS, {"number": "VLR-2026-000001"}),
    (BOOKINGS, {"trip_id": NOBODY}),
]


class TestTheGates:
    @pytest.mark.parametrize(("path", "params"), [*_STAFF_LOOKUPS, (AUDIT, {"actor_id": NOBODY})])
    def test_a_passenger_may_look_up_nothing(
        self, client: TestClient, rider: dict, path: str, params: dict
    ) -> None:
        assert client.get(path, headers=rider, params=params).status_code == 403

    @pytest.mark.parametrize(("path", "params"), _STAFF_LOOKUPS)
    def test_a_dispatcher_may_look_up_what_staff_may_see(
        self, client: TestClient, desk: dict, path: str, params: dict
    ) -> None:
        answer = client.get(path, headers=desk["headers"], params=params)
        assert answer.status_code == 200, answer.text

    def test_the_audit_log_stays_with_administrators(
        self, client: TestClient, desk: dict
    ) -> None:
        """Filtering by actor is still reading the log, and reading the log is
        require_admin: a dispatcher may not look up what his colleagues did."""
        answer = client.get(
            AUDIT, headers=desk["headers"], params={"actor_id": desk["user_id"]}
        )
        assert answer.status_code == 403
