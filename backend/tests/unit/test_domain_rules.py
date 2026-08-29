"""Domain rules.

These run with no database, no fixtures and no framework. If one of them ever
needs a session, the layering has been broken and the fix is the layering, not
the test.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from domain.booking import Booking
from domain.driver import Driver, DriverDocument, Vehicle
from domain.enums import (
    BookingStatus,
    DocumentStatus,
    DriverApprovalStatus,
    RideKind,
    SeatStatus,
    TripStatus,
)
from domain.fare import CommissionSplit, FareComponent, FareQuote, FareRule
from domain.identity import OtpChallenge, PhoneNumber
from domain.lifecycles import BOOKING_LIFECYCLE, TRIP_LIFECYCLE
from domain.route import Route, RouteStop
from domain.trip import Trip, TripSeat
from shared.errors import AuthenticationError, ConflictError, ValidationError
from shared.money import CurrencyMismatchError, Money

NOW = datetime(2026, 8, 29, 7, 0, tzinfo=UTC)


# -- money ---------------------------------------------------------------

class TestMoney:
    def test_float_is_refused_everywhere_money_flows(self) -> None:
        with pytest.raises(TypeError):
            Money(500.0)                       # type: ignore[arg-type]
        with pytest.raises(TypeError):
            Money.of_major(12.5)               # type: ignore[arg-type]
        with pytest.raises(TypeError):
            Money(50_000) * 1.5                # type: ignore[operator]

    def test_currencies_never_mix_implicitly(self) -> None:
        with pytest.raises(CurrencyMismatchError):
            Money(100, "AFN") + Money(100, "USD")

    def test_major_units_parse_without_precision_loss(self) -> None:
        assert Money.of_major("500", "AFN").amount_minor == 50_000
        assert Money.of_major("12.50", "AFN").amount_minor == 1_250
        assert Money.of_major("0.005", "AFN").amount_minor == 1     # ROUND_HALF_UP

    @pytest.mark.parametrize("amount", [1, 3, 7, 99, 333, 3333, 50_000, 123_457])
    def test_a_commission_split_always_closes(self, amount: int) -> None:
        """Rounding must never lose or invent an afghani."""
        split = CommissionSplit.of(Money(amount), 1000)
        assert split.platform + split.driver == split.gross

    def test_commission_matches_the_specification_example(self) -> None:
        # Section 33: 500 AFN at 10% is 50 to the platform, 450 to the driver.
        split = CommissionSplit.of(Money.of_major("500"), 1000)
        assert split.platform.as_major() == 50
        assert split.driver.as_major() == 450

    def test_an_impossible_rate_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            CommissionSplit.of(Money(1000), 10_001)


# -- lifecycles ----------------------------------------------------------

class TestTripLifecycle:
    def _trip(self, status: TripStatus = TripStatus.SCHEDULED, capacity: int = 4) -> Trip:
        return Trip(
            id="t", number="VLR-2026-000001", route_id="r", ride_kind=RideKind.SHARED,
            seat_capacity=capacity, scheduled_departure_at=NOW + timedelta(hours=2),
            status=status, origin_station_id="s", destination_id="d",
            seats=[TripSeat(id=f"s{i}", trip_id="t", seat_number=i)
                   for i in range(1, capacity + 1)],
        )

    def test_every_illegal_transition_raises(self) -> None:
        """The transition table is the only thing with an opinion about order."""
        for current in TripStatus:
            for target in TripStatus:
                trip = self._trip(current)
                if TRIP_LIFECYCLE.can(current, target):
                    trip.transition_to(target, at=NOW)
                    assert trip.status is target
                else:
                    with pytest.raises(ConflictError) as exc:
                        trip.transition_to(target, at=NOW)
                    assert exc.value.code == "TRIP_INVALID_TRANSITION"

    def test_a_completed_trip_is_terminal(self) -> None:
        assert TRIP_LIFECYCLE.is_terminal(TripStatus.COMPLETED)
        assert TRIP_LIFECYCLE.allowed_from(TripStatus.COMPLETED) == frozenset()

    def test_a_moving_vehicle_cannot_be_cancelled(self) -> None:
        """An interrupted journey is an incident, not a status change."""
        assert not TRIP_LIFECYCLE.can(TripStatus.IN_TRANSIT, TripStatus.CANCELLED)

    def test_timestamps_are_stamped_by_the_transition(self) -> None:
        trip = self._trip(TripStatus.BOARDING)
        trip.transition_to(TripStatus.IN_TRANSIT, at=NOW)
        assert trip.started_at == NOW
        trip.transition_to(TripStatus.ARRIVED, at=NOW)
        trip.transition_to(TripStatus.COMPLETED, at=NOW + timedelta(hours=1))
        assert trip.completed_at == NOW + timedelta(hours=1)

    def test_capacity_cannot_be_exceeded_by_construction(self) -> None:
        with pytest.raises(ConflictError) as exc:
            Trip(
                id="t", number="n", route_id="r", ride_kind=RideKind.SHARED,
                seat_capacity=2, scheduled_departure_at=NOW, status=TripStatus.SCHEDULED,
                origin_station_id="s", destination_id="d",
                seats=[TripSeat(id=f"s{i}", trip_id="t", seat_number=i) for i in range(1, 4)],
            )
        assert exc.value.code == "TRIP_CAPACITY_EXCEEDED"

    def test_booking_more_seats_than_remain_is_refused(self) -> None:
        trip = self._trip()
        trip.seats[0].reserve("b1")
        trip.seats[1].reserve("b1")
        with pytest.raises(ConflictError) as exc:
            trip.assert_bookable(3)
        assert exc.value.code == "TRIP_SEATS_UNAVAILABLE"
        assert exc.value.context["available"] == 2

    def test_a_departed_trip_takes_no_more_bookings(self) -> None:
        trip = self._trip(TripStatus.IN_TRANSIT)
        with pytest.raises(ConflictError) as exc:
            trip.assert_bookable(1)
        assert exc.value.code == "TRIP_DEPARTED"

    def test_a_status_string_from_storage_is_coerced(self) -> None:
        """A raw string compared by identity against a StrEnum silently reads as
        unavailable; the entity coerces so no mapper can reintroduce that."""
        seat = TripSeat(id="s", trip_id="t", seat_number=1, status="AVAILABLE")
        assert seat.status is SeatStatus.AVAILABLE
        assert seat.is_available


class TestSeats:
    def test_a_reserved_seat_cannot_be_reserved_again(self) -> None:
        seat = TripSeat(id="s", trip_id="t", seat_number=1)
        seat.reserve("b1")
        with pytest.raises(ConflictError) as exc:
            seat.reserve("b2")
        assert exc.value.code == "TRIP_SEATS_UNAVAILABLE"

    def test_releasing_returns_a_seat_to_the_pool(self) -> None:
        seat = TripSeat(id="s", trip_id="t", seat_number=1)
        seat.reserve("b1")
        seat.release()
        assert seat.is_available and seat.booking_id is None

    def test_a_blocked_seat_is_not_released_by_a_cancellation(self) -> None:
        seat = TripSeat(id="s", trip_id="t", seat_number=1)
        seat.block()
        with pytest.raises(ConflictError):
            seat.release()

    def test_a_booked_seat_cannot_be_blocked(self) -> None:
        seat = TripSeat(id="s", trip_id="t", seat_number=1)
        seat.reserve("b1")
        with pytest.raises(ConflictError):
            seat.block()


# -- bookings ------------------------------------------------------------

def _quote(seats: int = 1, kind: RideKind = RideKind.SHARED) -> FareQuote:
    return FareQuote(
        components=(FareComponent("fare.component.seat", Money.of_major("500"), seats),),
        currency="AFN", ride_kind=kind, seat_count=seats, route_id="r",
        from_sequence=0, to_sequence=2,
    )


def _booking(status: BookingStatus = BookingStatus.PENDING) -> Booking:
    booking = Booking.from_quote(
        id="b", number="BKG-2026-000001", trip_id="t", passenger_id="p",
        quote=_quote(), seat_ids=["s1"], seat_numbers=[1],
        pickup_station_id="st", dropoff_destination_id="d", verification_code="7K4Q",
    )
    while booking.status is not status:
        nxt = next(iter(sorted(BOOKING_LIFECYCLE.allowed_from(booking.status), key=str)))
        route = BOOKING_LIFECYCLE.path(booking.status, status)
        booking.transition_to(route[0] if route else nxt, at=NOW)
    return booking


class TestBooking:
    def test_the_fare_is_frozen_onto_the_booking(self) -> None:
        """Changing a route price tomorrow must not change what was charged today."""
        booking = _booking()
        assert booking.fare_total == Money.of_major("500")
        assert booking.fare_breakdown[0]["amount_minor"] == 50_000

    def test_seat_numbers_are_stored_in_order(self) -> None:
        booking = Booking.from_quote(
            id="b", number="n", trip_id="t", passenger_id="p", quote=_quote(2),
            seat_ids=["s2", "s1"], seat_numbers=[3, 1],
            pickup_station_id="st", dropoff_destination_id="d", verification_code="AB12",
        )
        assert booking.seat_numbers == [1, 3]

    def test_seat_allocation_must_match_the_quote(self) -> None:
        with pytest.raises(ConflictError):
            Booking.from_quote(
                id="b", number="n", trip_id="t", passenger_id="p", quote=_quote(2),
                seat_ids=["s1"], seat_numbers=[1],
                pickup_station_id="st", dropoff_destination_id="d", verification_code="AB12",
            )

    def test_stops_must_be_in_travelling_order(self) -> None:
        with pytest.raises(ValidationError) as exc:
            Booking(
                id="b", number="n", trip_id="t", passenger_id="p",
                ride_kind=RideKind.SHARED, seat_count=1, seat_numbers=[1],
                pickup_sequence=3, dropoff_sequence=1,
                pickup_station_id="st", dropoff_destination_id="d",
                fare_total=Money(1000), fare_breakdown=(),
            )
        assert exc.value.code == "BOOKING_STOPS_OUT_OF_ORDER"

    def test_a_wrong_verification_code_does_not_board_a_passenger(self) -> None:
        booking = _booking(BookingStatus.READY)
        with pytest.raises(ConflictError) as exc:
            booking.verify("WRONG", at=NOW)
        assert exc.value.code == "BOOKING_VERIFICATION_FAILED"
        assert booking.status is BookingStatus.READY

    def test_verification_ignores_case_and_whitespace(self) -> None:
        booking = _booking(BookingStatus.READY)
        booking.verify("  7k4q ", at=NOW)
        assert booking.status is BookingStatus.ONBOARD

    def test_a_passenger_aboard_cannot_cancel(self) -> None:
        booking = _booking(BookingStatus.ONBOARD)
        with pytest.raises(ConflictError) as exc:
            booking.cancel(by_role="PASSENGER", reason_code="OTHER", at=NOW)
        assert exc.value.code == "BOOKING_NOT_CANCELLABLE"

    def test_a_cancelled_booking_is_never_resurrected_by_a_cascade(self) -> None:
        booking = _booking(BookingStatus.CONFIRMED)
        booking.cancel(by_role="PASSENGER", reason_code="OTHER", at=NOW)
        booking.follow_trip(BookingStatus.COMPLETED, at=NOW)
        assert booking.status is BookingStatus.CANCELLED

    def test_a_lagging_booking_catches_up_through_the_declared_path(self) -> None:
        """A missed intermediate cascade must not strand a passenger."""
        booking = _booking(BookingStatus.CONFIRMED)
        booking.follow_trip(BookingStatus.READY, at=NOW)
        assert booking.status is BookingStatus.READY

    def test_a_cascade_never_routes_through_cancellation(self) -> None:
        booking = _booking(BookingStatus.CONFIRMED)
        booking.follow_trip(BookingStatus.NO_SHOW, at=NOW)
        assert booking.status in (BookingStatus.NO_SHOW, BookingStatus.CONFIRMED)
        assert booking.status is not BookingStatus.CANCELLED


# -- routes --------------------------------------------------------------

class TestRoute:
    def _route(self) -> Route:
        stops = [
            RouteStop(id="1", route_id="r", sequence=0, station_id="khishki",
                      is_pickup=True, is_dropoff=False),
            RouteStop(id="2", route_id="r", sequence=1, destination_id="siahgird"),
            RouteStop(id="3", route_id="r", sequence=2, destination_id="charikar",
                      is_pickup=False, is_dropoff=True),
        ]
        from domain.enums import RouteType

        return Route(
            id="r", code="R1", route_type=RouteType.INTERCITY,
            origin_station_id="khishki", destination_id="charikar", stops=stops,
        )

    def test_a_route_serves_an_intermediate_leg(self) -> None:
        """Boarding at a village on a longer run is the normal case here."""
        route = self._route()
        assert route.serves("khishki", "charikar")
        assert route.serves("siahgird", "charikar")
        assert route.segment("siahgird", "charikar") == (1, 2)

    def test_a_route_does_not_serve_the_reverse_direction(self) -> None:
        route = self._route()
        assert not route.serves("charikar", "khishki")
        with pytest.raises(ConflictError) as exc:
            route.segment("charikar", "khishki")
        assert exc.value.code == "ROUTE_NOT_RESOLVABLE"

    def test_a_drop_off_only_stop_cannot_be_boarded_at(self) -> None:
        route = self._route()
        assert not route.serves("charikar", "charikar")

    def test_a_stop_must_name_exactly_one_place(self) -> None:
        with pytest.raises(ValidationError):
            RouteStop(id="1", route_id="r", sequence=0)
        with pytest.raises(ValidationError):
            RouteStop(id="1", route_id="r", sequence=0, station_id="a", destination_id="b")


# -- fares ---------------------------------------------------------------

class TestFare:
    def test_a_negative_fare_is_impossible(self) -> None:
        from datetime import date

        with pytest.raises(ValidationError) as exc:
            FareRule(
                id="f", route_id="r", ride_kind=RideKind.SHARED, vehicle_type_code=None,
                from_sequence=0, to_sequence=2, amount=Money(-1),
                valid_from=date(2026, 1, 1),
            )
        assert exc.value.code == "FARE_NEGATIVE"

    def test_a_quote_totals_its_components(self) -> None:
        quote = FareQuote(
            components=(
                FareComponent("fare.component.seat", Money.of_major("500"), 2),
                FareComponent("fare.component.luggage", Money.of_major("50"), 1),
            ),
            currency="AFN", ride_kind=RideKind.SHARED, seat_count=2, route_id="r",
            from_sequence=0, to_sequence=1,
        )
        assert quote.total() == Money.of_major("1050")
        assert quote.per_seat() == Money.of_major("525")

    def test_a_quote_cannot_mix_currencies(self) -> None:
        with pytest.raises(ValidationError):
            FareQuote(
                components=(FareComponent("k", Money(100, "USD")),),
                currency="AFN", ride_kind=RideKind.SHARED, seat_count=1,
                route_id="r", from_sequence=0, to_sequence=1,
            )


# -- drivers -------------------------------------------------------------

class TestDriver:
    def test_an_unapproved_driver_cannot_work(self) -> None:
        with pytest.raises(ConflictError) as exc:
            Driver(id="d", user_id="u").assert_can_work()
        assert exc.value.code == "DRIVER_NOT_APPROVED"

    def test_approval_requires_every_document(self) -> None:
        driver = Driver(id="d", user_id="u")
        with pytest.raises(ConflictError) as exc:
            driver.approve(by="a", at=NOW, required_documents=frozenset({"LICENSE"}))
        assert exc.value.code == "DRIVER_DOCUMENTS_INCOMPLETE"
        assert exc.value.context["missing"] == ["LICENSE"]

    def test_an_expired_document_does_not_count(self) -> None:
        driver = Driver(
            id="d", user_id="u",
            documents=[
                DriverDocument(
                    id="1", driver_id="d", document_type_code="LICENSE", file_key="k",
                    status=DocumentStatus.VERIFIED, expires_on=NOW.date() - timedelta(days=1),
                )
            ],
        )
        assert driver.missing_documents(frozenset({"LICENSE"}), on=NOW.date()) == {"LICENSE"}

    def test_an_approved_driver_whose_licence_expired_cannot_work(self) -> None:
        """Approval is a moment; a licence is a period.

        The driver sent everything, an administrator checked it, approval was
        granted -- and then the licence ran out. `assert_can_work` only reads
        approval_status, so nothing about that driver's record changes on the
        day their permit expires. This is the check that has to notice.
        """
        driver = Driver(
            id="d", user_id="u",
            approval_status=DriverApprovalStatus.APPROVED,
            documents=[
                DriverDocument(
                    id="1", driver_id="d", document_type_code="LICENSE", file_key="k",
                    status=DocumentStatus.VERIFIED,
                    expires_on=NOW.date() - timedelta(days=1),
                )
            ],
        )
        # Still approved -- which is exactly the problem.
        driver.assert_can_work()

        with pytest.raises(ConflictError) as exc:
            driver.assert_documents_current(frozenset({"LICENSE"}), on=NOW.date())
        assert exc.value.code == "DRIVER_DOCUMENTS_EXPIRED"
        assert exc.value.context["documents"] == ["LICENSE"]

    def test_a_licence_valid_today_is_still_good_on_its_last_day(self) -> None:
        driver = Driver(
            id="d", user_id="u",
            approval_status=DriverApprovalStatus.APPROVED,
            documents=[
                DriverDocument(
                    id="1", driver_id="d", document_type_code="LICENSE", file_key="k",
                    status=DocumentStatus.VERIFIED, expires_on=NOW.date(),
                )
            ],
        )
        driver.assert_documents_current(frozenset({"LICENSE"}), on=NOW.date())

    def test_the_expiry_check_fails_closed_when_documents_were_not_loaded(self) -> None:
        """A caller that forgets to load the documents stops the driver.

        The alternative -- an empty list reading as "nothing expired" -- turns a
        forgotten join into an unlicensed driver carrying passengers, and no
        test would ever catch it.
        """
        driver = Driver(
            id="d", user_id="u", approval_status=DriverApprovalStatus.APPROVED,
        )
        with pytest.raises(ConflictError) as exc:
            driver.assert_documents_current(frozenset({"LICENSE"}), on=NOW.date())
        assert exc.value.code == "DRIVER_DOCUMENTS_EXPIRED"

    def test_a_document_with_no_expiry_never_goes_stale(self) -> None:
        """A tazkira does not run out; only the permits carry a date."""
        driver = Driver(
            id="d", user_id="u",
            approval_status=DriverApprovalStatus.APPROVED,
            documents=[
                DriverDocument(
                    id="1", driver_id="d", document_type_code="NATIONAL_ID",
                    file_key="k", status=DocumentStatus.VERIFIED, expires_on=None,
                )
            ],
        )
        driver.assert_documents_current(
            frozenset({"NATIONAL_ID"}), on=NOW.date() + timedelta(days=3650)
        )

    def test_a_suspended_driver_is_refused_before_anything_else(self) -> None:
        driver = Driver(id="d", user_id="u", approval_status=DriverApprovalStatus.APPROVED)
        driver.suspend("documents expired")
        with pytest.raises(ConflictError) as exc:
            driver.assert_can_work()
        assert exc.value.code == "DRIVER_SUSPENDED"

    def test_a_driver_on_a_trip_cannot_go_offline(self) -> None:
        from domain.enums import DriverAvailability

        driver = Driver(
            id="d", user_id="u", approval_status=DriverApprovalStatus.APPROVED,
            availability=DriverAvailability.ON_TRIP,
        )
        with pytest.raises(ConflictError) as exc:
            driver.go_offline()
        assert exc.value.code == "DRIVER_ALREADY_ON_TRIP"

    def test_rating_average_is_exact(self) -> None:
        driver = Driver(id="d", user_id="u")
        for score in (5, 4, 4):
            driver.record_rating(score)
        assert driver.rating_average == 4.33

    def test_a_rating_outside_one_to_five_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            Driver(id="d", user_id="u").record_rating(6)

    def test_a_vehicle_needs_a_plate_and_seats(self) -> None:
        with pytest.raises(ValidationError):
            Vehicle(id="v", driver_id="d", vehicle_type_code="SEDAN",
                    plate_number="  ", seat_capacity=4)
        with pytest.raises(ValidationError):
            Vehicle(id="v", driver_id="d", vehicle_type_code="SEDAN",
                    plate_number="PRW-1", seat_capacity=0)


# -- identity ------------------------------------------------------------

class TestPhoneNumber:
    @pytest.mark.parametrize(
        "raw",
        ["0700123456", "+93700123456", "0093 700 123 456", "93700123456", "+93 700 123 456"],
    )
    def test_afghan_numbers_normalise_to_one_form(self, raw: str) -> None:
        assert PhoneNumber.parse(raw).value == "+93700123456"

    def test_a_number_is_masked_for_logs_and_error_contexts(self) -> None:
        masked = PhoneNumber.parse("0700123456").masked
        assert "700123" not in masked
        assert masked.startswith("+937")

    def test_an_implausible_number_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            PhoneNumber("+1")


class TestOtp:
    def _challenge(self, **kw) -> OtpChallenge:
        defaults = {
            "id": "o", "phone": PhoneNumber("+93700123456"), "code_hash": "hash",
            "expires_at": NOW + timedelta(minutes=5), "max_attempts": 3,
        }
        return OtpChallenge(**{**defaults, **kw})

    def test_a_correct_code_consumes_the_challenge(self) -> None:
        challenge = self._challenge()
        challenge.verify("hash", at=NOW)
        assert challenge.is_consumed

    def test_a_consumed_challenge_cannot_be_reused(self) -> None:
        challenge = self._challenge()
        challenge.verify("hash", at=NOW)
        with pytest.raises(ConflictError) as exc:
            challenge.verify("hash", at=NOW)
        assert exc.value.code == "OTP_ALREADY_CONSUMED"

    def test_an_expired_code_is_refused(self) -> None:
        challenge = self._challenge()
        with pytest.raises(AuthenticationError) as exc:
            challenge.verify("hash", at=NOW + timedelta(minutes=6))
        assert exc.value.code == "OTP_EXPIRED"

    def test_attempts_are_counted_and_then_exhausted(self) -> None:
        challenge = self._challenge()
        for _ in range(3):
            with pytest.raises(AuthenticationError):
                challenge.verify("wrong", at=NOW)
        assert challenge.attempts == 3
        with pytest.raises(AuthenticationError) as exc:
            challenge.verify("hash", at=NOW)
        assert exc.value.code == "OTP_ATTEMPTS_EXCEEDED"

    def test_a_failed_attempt_reports_what_remains(self) -> None:
        challenge = self._challenge()
        with pytest.raises(AuthenticationError) as exc:
            challenge.verify("wrong", at=NOW)
        assert exc.value.context["attempts_remaining"] == 2


class TestDriverDocumentCurrency:
    """Only the newest upload of each type counts.

    A driver who replaces a licence is presenting the new photograph. Letting
    the superseded one still satisfy the requirement would let an administrator
    approve someone whose current licence nobody has looked at -- which is the
    one thing the approval gate exists to prevent.
    """

    def _driver(self, *documents: DriverDocument) -> Driver:
        return Driver(id="d", user_id="u", documents=list(documents))

    def _document(self, status: DocumentStatus, days_ago: int, kind: str = "LICENSE"):
        return DriverDocument(
            id=f"{kind}-{days_ago}",
            driver_id="d",
            document_type_code=kind,
            file_key="k",
            status=status,
            uploaded_at=NOW - timedelta(days=days_ago),
        )

    def test_a_pending_replacement_supersedes_a_verified_original(self) -> None:
        driver = self._driver(
            self._document(DocumentStatus.VERIFIED, days_ago=5),
            self._document(DocumentStatus.PENDING, days_ago=0),
        )
        assert driver.current_documents()["LICENSE"].status is DocumentStatus.PENDING
        assert driver.missing_documents(frozenset({"LICENSE"}), on=NOW.date()) == {"LICENSE"}

    def test_a_verified_replacement_satisfies_the_requirement(self) -> None:
        driver = self._driver(
            self._document(DocumentStatus.REJECTED, days_ago=5),
            self._document(DocumentStatus.VERIFIED, days_ago=0),
        )
        assert driver.missing_documents(frozenset({"LICENSE"}), on=NOW.date()) == frozenset()

    def test_a_driver_with_a_replaced_licence_cannot_be_approved(self) -> None:
        driver = self._driver(
            self._document(DocumentStatus.VERIFIED, days_ago=5),
            self._document(DocumentStatus.PENDING, days_ago=0),
        )
        with pytest.raises(ConflictError) as exc:
            driver.approve(
                by="admin", at=NOW, required_documents=frozenset({"LICENSE"})
            )
        assert exc.value.code == "DRIVER_DOCUMENTS_INCOMPLETE"

    def test_documents_of_different_types_do_not_supersede_each_other(self) -> None:
        driver = self._driver(
            self._document(DocumentStatus.VERIFIED, days_ago=1, kind="LICENSE"),
            self._document(DocumentStatus.VERIFIED, days_ago=0, kind="NATIONAL_ID"),
        )
        assert driver.missing_documents(
            frozenset({"LICENSE", "NATIONAL_ID"}), on=NOW.date()
        ) == frozenset()

    def test_an_expired_current_document_does_not_count(self) -> None:
        driver = self._driver(
            DriverDocument(
                id="1", driver_id="d", document_type_code="LICENSE", file_key="k",
                status=DocumentStatus.VERIFIED,
                expires_on=NOW.date() - timedelta(days=1),
                uploaded_at=NOW,
            )
        )
        assert driver.missing_documents(frozenset({"LICENSE"}), on=NOW.date()) == {"LICENSE"}
