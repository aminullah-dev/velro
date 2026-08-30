"""Agreeing a fare between a passenger and a driver, section 89.

Three moves: a passenger asks at a price, drivers answer with a price, the
passenger picks one. Nothing here computes a fare -- VELRO does not know the
distance between two villages in Ghorband or which stretch of road is dirt, and
inventing a number would be worse than asking the two people who do know.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from domain.enums import ActorRole, FareOfferStatus, RideRequestStatus
from domain.negotiation import FareOffer, assert_offer_allowed, total_fare
from shared import error_codes
from shared.clock import Clock
from shared.errors import (
    ConflictError,
    NotFoundError,
    PermissionError,
    ValidationError,
)
from shared.ids import IdGenerator
from shared.logging import get_logger
from shared.money import Money

log = get_logger(__name__)

# How long a request stays on the drivers' board. Long enough for someone to
# finish a journey and look, short enough that a passenger is not still being
# offered a ride they gave up on an hour ago.
DEFAULT_REQUEST_TTL_MINUTES = 45

# How far ahead a journey may be arranged. Two weeks is well beyond how far
# anyone in Ghorband plans a car and well short of a request sitting open for a
# season; it is an app_settings key so it can be moved without a deploy.
DEFAULT_REQUEST_HORIZON_DAYS = 14

# Clocks on cheap handsets drift, and a passenger who taps "now" sends the
# instant they tapped, not the instant the server reads it. This is slack for
# that, not a licence to book the past.
DEPARTURE_GRACE_MINUTES = 10

# A scheduled request closes shortly before its departure rather than at it:
# a driver who accepts ninety seconds before the car should leave has accepted
# nothing anybody can act on.
DEPARTURE_CLOSING_LEAD_MINUTES = 30


@dataclass(frozen=True, slots=True)
class RequestRideCommand:
    passenger_id: str
    origin_station_id: str
    destination_id: str
    passenger_count: int
    offered_fare_minor: int
    # The return leg's fare, when there is a return. None means one way; it is
    # never "a return costing nothing".
    return_fare_minor: int | None = None
    currency: str = "AFN"
    vehicle_type_code: str | None = None
    note: str | None = None
    requested_for: datetime | None = None
    return_for: datetime | None = None
    request_id: str | None = None


class RequestRide:
    """The passenger names a price."""

    def __init__(
        self, *, requests, geography, settings, audit, clock: Clock, new_id: IdGenerator
    ) -> None:
        self._requests = requests
        self._geography = geography
        self._settings = settings
        self._audit = audit
        self._clock = clock
        self._new_id = new_id

    def execute(self, cmd: RequestRideCommand):
        if cmd.offered_fare_minor <= 0:
            raise ConflictError(
                error_codes.FARE_OFFER_AMOUNT_INVALID,
                amount_minor=cmd.offered_fare_minor,
            )
        if cmd.return_fare_minor is not None and cmd.return_fare_minor <= 0:
            raise ConflictError(
                error_codes.FARE_OFFER_AMOUNT_INVALID,
                amount_minor=cmd.return_fare_minor,
            )
        if self._geography.find_station(cmd.origin_station_id) is None:
            raise NotFoundError(
                error_codes.STATION_NOT_FOUND, station_id=cmd.origin_station_id
            )
        if self._geography.find_destination(cmd.destination_id) is None:
            raise NotFoundError(
                error_codes.DESTINATION_NOT_FOUND, destination_id=cmd.destination_id
            )

        now = self._clock.now()

        # When the passenger wants to travel, which is not the same as when
        # they are asking.
        #
        # The column has always been here and has always been filled with
        # `now`, because nothing above the use case ever passed anything else.
        # That silently made VELRO a hail-a-car app: every request meant "a
        # car, immediately". Somebody arranging tomorrow's journey to Kabul the
        # night before -- which is how most of these journeys are actually
        # arranged -- had no way to say so.
        requested_for = cmd.requested_for or now
        grace = timedelta(minutes=DEPARTURE_GRACE_MINUTES)
        if requested_for < now - grace:
            # Not a validation nicety. A request in the past would sit on the
            # board looking live, and the trip created from it would inherit a
            # departure that has already been and gone.
            raise ConflictError(
                error_codes.RIDE_REQUEST_DEPARTURE_PAST,
                requested_for=requested_for.isoformat(),
            )
        horizon_days = self._settings.get_int(
            "ride_request.horizon_days", DEFAULT_REQUEST_HORIZON_DAYS
        )
        if requested_for > now + timedelta(days=horizon_days):
            raise ConflictError(
                error_codes.RIDE_REQUEST_DEPARTURE_TOO_FAR,
                requested_for=requested_for.isoformat(),
                horizon_days=horizon_days,
            )

        # The way back, if they want one.
        #
        # In Ghorband a car to Charikar or Kabul is hired for the journey and
        # the return together: one car, one driver, one price argued once. The
        # return is rarely the same day, which is exactly why it has to be
        # asked for up front -- a passenger who negotiates only the outbound is
        # a passenger who has to find a car again from the other end, in a town
        # that is not theirs.
        #
        # It is validated against the departure, not against now: a return
        # before the outbound is not a late booking, it is a nonsense.
        return_for = cmd.return_for
        if return_for is not None and return_for <= requested_for:
            raise ConflictError(
                error_codes.RIDE_REQUEST_RETURN_BEFORE_DEPARTURE,
                requested_for=requested_for.isoformat(),
                return_for=return_for.isoformat(),
            )
        if return_for is not None and return_for > now + timedelta(days=horizon_days):
            raise ConflictError(
                error_codes.RIDE_REQUEST_DEPARTURE_TOO_FAR,
                requested_for=return_for.isoformat(),
                horizon_days=horizon_days,
            )

        # One open request at a time. A passenger with three live requests is
        # taking three drivers off the board for one journey.
        #
        # ``at`` is what stops a request nobody answered from blocking them for
        # ever: the row may still say OPEN until someone reads it, but a
        # deadline that has passed does not hold a place.
        open_already = self._requests.find_open_for_passenger(cmd.passenger_id, at=now)
        if open_already is not None:
            # Its id travels with the error so the app can offer the way back
            # rather than only the refusal. Being told "no" with no route to the
            # thing saying no is what makes a person reinstall the app.
            raise ConflictError(
                error_codes.RIDE_REQUEST_ALREADY_OPEN,
                ride_request_id=open_already.id,
            )
        ttl = self._settings.get_int(
            "ride_request.ttl_minutes", DEFAULT_REQUEST_TTL_MINUTES
        )
        # A request stays open until shortly before the journey it is for.
        #
        # The deadline used to be `now + ttl` whatever the departure, which is
        # right for "I am standing at the station" and useless for anything
        # else: a request made tonight for tomorrow's six o'clock would have
        # closed before midnight, with the passenger still waiting and no
        # driver able to take it. Immediate requests are unaffected --
        # `requested_for` is `now`, so the lead time lands in the past and the
        # TTL wins.
        closing_lead = timedelta(minutes=DEPARTURE_CLOSING_LEAD_MINUTES)
        expires_at = max(now + timedelta(minutes=ttl), requested_for - closing_lead)
        row = self._requests.create(
            id=self._new_id(),
            passenger_id=cmd.passenger_id,
            origin_station_id=cmd.origin_station_id,
            destination_id=cmd.destination_id,
            passenger_count=cmd.passenger_count,
            vehicle_type_code=cmd.vehicle_type_code,
            requested_for=requested_for,
            return_for=return_for,
            expires_at=expires_at,
            status=RideRequestStatus.OPEN.value,
            offered_fare_minor=cmd.offered_fare_minor,
            return_fare_minor=cmd.return_fare_minor if return_for else None,
            offered_fare_currency=cmd.currency,
            note=cmd.note,
        )
        self._audit.write(
            "ride_request.created",
            actor_id=cmd.passenger_id,
            actor_role=ActorRole.PASSENGER,
            entity_type="ride_request",
            entity_id=row.id,
            after={
                "offered_fare_minor": cmd.offered_fare_minor,
                "currency": cmd.currency,
                "passengers": cmd.passenger_count,
            },
            request_id=cmd.request_id,
        )
        return row


@dataclass(frozen=True, slots=True)
class OfferFareCommand:
    ride_request_id: str
    driver_user_id: str
    amount_minor: int
    # The driver's price for the way back. Required exactly when the request
    # asked for a return, and refused when it did not.
    return_amount_minor: int | None = None
    note: str | None = None
    request_id: str | None = None


class OfferFare:
    """A driver answers with a price.

    A driver happy with the asking price offers exactly that number. There is no
    separate "accept": one path means one set of rules, and the passenger's list
    reads the same whether a driver agreed or countered.
    """

    def __init__(
        self, *, requests, offers, drivers, vehicles, audit, notifier=None,
        clock: Clock, new_id: IdGenerator,
    ) -> None:
        self._requests = requests
        self._offers = offers
        self._drivers = drivers
        self._vehicles = vehicles
        self._audit = audit
        self._notifier = notifier
        self._clock = clock
        self._new_id = new_id

    def execute(self, cmd: OfferFareCommand) -> FareOffer:
        driver = self._drivers.find_by_user(cmd.driver_user_id)
        if driver is None:
            raise NotFoundError(
                error_codes.DRIVER_NOT_FOUND, user_id=cmd.driver_user_id
            )
        row = self._requests.find(cmd.ride_request_id)
        if row is None:
            raise NotFoundError(
                error_codes.RIDE_REQUEST_NOT_FOUND, ride_request_id=cmd.ride_request_id
            )

        now = self._clock.now()
        # An expired request is closed the moment anyone looks at it, rather
        # than waiting for a job that may not have run.
        status = RideRequestStatus(row.status)
        if status is RideRequestStatus.OPEN and row.expires_at <= now:
            row.status = RideRequestStatus.EXPIRED.value
            self._requests.save(row)
            status = RideRequestStatus.EXPIRED

        # Both sides compared as totals. The legs are argued separately and
        # checked together: a driver could otherwise put a sensible number on
        # the outbound and an absurd one on the return and walk past every
        # plausibility guard on the way.
        currency = row.offered_fare_currency
        asking = total_fare(
            Money(row.offered_fare_minor, currency),
            Money(row.return_fare_minor, currency) if row.return_fare_minor else None,
        )
        offered = total_fare(
            Money(cmd.amount_minor, currency),
            Money(cmd.return_amount_minor, currency) if cmd.return_amount_minor else None,
        )
        # A return leg may only be priced where a return was asked for, and one
        # that was asked for may not be silently left out of the answer.
        if bool(cmd.return_amount_minor) != bool(row.return_fare_minor):
            raise ValidationError(
                error_codes.FARE_OFFER_RETURN_MISMATCH,
                ride_request_id=row.id,
            )
        assert_offer_allowed(
            asking=asking,
            offered=offered,
            request_status=status,
            already_offered=self._offers.open_for(row.id, driver.id) is not None,
            driver_is_passenger=row.passenger_id == cmd.driver_user_id,
        )

        vehicle = self._vehicles.current_for_driver(driver.id)
        created = self._offers.create(
            id=self._new_id(),
            ride_request_id=row.id,
            driver_id=driver.id,
            vehicle_id=vehicle.id if vehicle else None,
            amount_minor=cmd.amount_minor,
            return_amount_minor=cmd.return_amount_minor,
            amount_currency=offered.currency,
            status=FareOfferStatus.OFFERED.value,
            note=cmd.note,
        )
        self._audit.write(
            "fare_offer.made",
            actor_id=cmd.driver_user_id,
            actor_role=ActorRole.DRIVER,
            entity_type="fare_offer",
            entity_id=created.id,
            after={
                "ride_request_id": row.id,
                "amount_minor": offered.amount_minor,
                "asking_minor": asking.amount_minor,
            },
            request_id=cmd.request_id,
        )
        # The passenger is not sitting on the offers screen. Telling them is the
        # difference between a negotiation and a message nobody reads.
        _tell(
            self._notifier,
            user_id=row.passenger_id,
            message_key="notify.offer.received",
            payload={
                "ride_request_id": row.id,
                "amount_minor": offered.amount_minor,
                "currency": offered.currency,
            },
        )
        return _to_offer(created)


@dataclass(frozen=True, slots=True)
class WithdrawOfferCommand:
    offer_id: str
    driver_user_id: str
    request_id: str | None = None


class WithdrawOffer:
    def __init__(self, *, offers, drivers, audit, clock: Clock) -> None:
        self._offers = offers
        self._drivers = drivers
        self._audit = audit
        self._clock = clock

    def execute(self, cmd: WithdrawOfferCommand) -> FareOffer:
        driver = self._drivers.find_by_user(cmd.driver_user_id)
        row = self._offers.find(cmd.offer_id)
        if row is None or driver is None or row.driver_id != driver.id:
            # The same answer whether it is someone else's or does not exist.
            raise NotFoundError(error_codes.FARE_OFFER_NOT_FOUND, offer_id=cmd.offer_id)

        offer = _to_offer(row)
        offer.withdraw(at=self._clock.now())
        row.status = offer.status.value
        row.responded_at = offer.responded_at
        row.version += 1
        self._offers.save(row)

        self._audit.write(
            "fare_offer.withdrawn",
            actor_id=cmd.driver_user_id,
            actor_role=ActorRole.DRIVER,
            entity_type="fare_offer",
            entity_id=row.id,
            request_id=cmd.request_id,
        )
        return offer


def _tell(notifier, **kwargs) -> None:
    """Best effort, always.

    A notification that cannot be sent must never undo a ride that was agreed.
    The row is written inside the same transaction either way, so the message is
    waiting in the app even when every channel failed.
    """
    if notifier is None:
        return
    try:
        notifier.notify(**kwargs)
    except Exception:
        log.warning("notify.failed", message_key=kwargs.get("message_key"))


def _to_offer(row) -> FareOffer:
    return FareOffer(
        id=row.id,
        ride_request_id=row.ride_request_id,
        driver_id=row.driver_id,
        amount=Money(row.amount_minor, row.amount_currency),
        return_amount=(
            Money(row.return_amount_minor, row.amount_currency)
            if getattr(row, "return_amount_minor", None)
            else None
        ),
        status=row.status,
        note=row.note,
        created_at=row.created_at,
        responded_at=row.responded_at,
    )


@dataclass(frozen=True, slots=True)
class AcceptOfferCommand:
    offer_id: str
    passenger_id: str
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class AcceptOfferResult:
    ride_request_id: str
    offer_id: str
    trip_id: str
    trip_number: str
    booking_id: str
    booking_number: str
    verification_code: str
    driver_id: str
    agreed_fare: Money


class AcceptOffer:
    """The passenger picks a driver, and the journey exists.

    This is the moment the fare is settled, so it is also the moment everything
    downstream is fixed: the trip, the seats, the booking, and the agreed amount
    copied onto the booking. A price agreed today must still explain a receipt
    read next month, so nothing here leaves the fare to be looked up again.
    """

    def __init__(
        self, *, requests, offers, trips, bookings, seats, drivers, vehicles,
        routes, geography, numbers, codes, audit, users=None, notifier=None,
        clock: Clock, new_id: IdGenerator,
    ) -> None:
        self._requests = requests
        self._offers = offers
        self._trips = trips
        self._bookings = bookings
        self._seats = seats
        self._drivers = drivers
        self._vehicles = vehicles
        self._routes = routes
        self._geography = geography
        self._numbers = numbers
        self._codes = codes
        self._audit = audit
        self._users = users
        self._notifier = notifier
        self._clock = clock
        self._new_id = new_id

    def execute(self, cmd: AcceptOfferCommand) -> AcceptOfferResult:
        from domain.booking import Booking
        from domain.enums import BookingStatus, RideKind, SeatStatus, TripStatus
        from domain.fare import FareComponent, FareQuote

        offer_row = self._offers.find(cmd.offer_id)
        if offer_row is None:
            raise NotFoundError(error_codes.FARE_OFFER_NOT_FOUND, offer_id=cmd.offer_id)
        request_row = self._requests.find(offer_row.ride_request_id)
        if request_row is None:
            raise NotFoundError(
                error_codes.RIDE_REQUEST_NOT_FOUND,
                ride_request_id=offer_row.ride_request_id,
            )
        if request_row.passenger_id != cmd.passenger_id:
            raise PermissionError(
                error_codes.PERMISSION_DENIED, offer_id=cmd.offer_id
            )

        now = self._clock.now()
        if RideRequestStatus(request_row.status) is not RideRequestStatus.OPEN:
            raise ConflictError(
                error_codes.RIDE_REQUEST_NOT_OPEN, current=request_row.status
            )

        offer = _to_offer(offer_row)
        offer.accept(at=now)

        driver = self._drivers.find(offer_row.driver_id)
        if driver is None:
            raise NotFoundError(
                error_codes.DRIVER_NOT_FOUND, driver_id=offer_row.driver_id
            )
        vehicle = self._vehicles.current_for_driver(driver.id)
        # Seats come from the vehicle when there is one: a Corolla cannot carry
        # a Hiace's worth of passengers because a request asked for it.
        capacity = max(
            request_row.passenger_count, vehicle.seat_capacity if vehicle else 0
        )

        route = self._routes.find_for(
            request_row.origin_station_id, request_row.destination_id
        )
        trip = self._trips.create(
            id=self._new_id(),
            number=self._numbers.allocate("trip", year=now.year),
            route_id=route.id if route else None,
            ride_kind=RideKind.PRIVATE.value,
            seat_capacity=capacity,
            scheduled_departure_at=request_row.requested_for,
            status=TripStatus.DRIVER_ASSIGNED.value,
            origin_station_id=request_row.origin_station_id,
            destination_id=request_row.destination_id,
            driver_id=driver.id,
            vehicle_id=vehicle.id if vehicle else None,
        )
        self._trips.session.flush()

        # Seats are rows, so capacity cannot be exceeded by construction --
        # the same guarantee a scheduled trip has.
        for n in range(1, capacity + 1):
            self._seats.create(
                id=self._new_id(), trip_id=trip.id, seat_number=n,
                status=SeatStatus.AVAILABLE.value,
            )
        self._trips.session.flush()

        # Through lock_available and reserve, exactly as a scheduled booking
        # goes. There is no contention on a trip created a line ago, but two
        # ways of taking a seat would mean two places for the guarantee to be
        # weakened later, and this is the mechanic the product rests on.
        taken = self._seats.lock_available(trip.id, request_row.passenger_count)

        # What actually changes hands: both legs together.
        #
        # Taking `amount_minor` alone would book a round trip at the price of
        # the outbound and quietly hand the driver's return fare to nobody --
        # the commission, the wallet and the passenger's receipt would all
        # agree with each other and all be wrong.
        agreed = total_fare(
            Money(offer_row.amount_minor, offer_row.amount_currency),
            Money(offer_row.return_amount_minor, offer_row.amount_currency)
            if offer_row.return_amount_minor
            else None,
        )
        # A quote of exactly one line, and that line says the price was agreed
        # rather than calculated. Going through FareQuote rather than building a
        # Booking by hand keeps one construction path, so the negotiated booking
        # is frozen and validated exactly as a scheduled one is.
        quote = FareQuote(
            components=(
                FareComponent(key="fare.component.agreed", amount=agreed, quantity=1),
            ),
            currency=agreed.currency,
            ride_kind=RideKind.PRIVATE,
            seat_count=request_row.passenger_count,
            route_id=route.id if route else None,
            from_sequence=0,
            to_sequence=1,
        )
        booking = Booking.from_quote(
            id=self._new_id(),
            number=self._numbers.allocate("booking", year=now.year),
            trip_id=trip.id,
            passenger_id=cmd.passenger_id,
            quote=quote,
            seat_ids=[s.id for s in taken],
            seat_numbers=[s.seat_number for s in taken],
            pickup_station_id=request_row.origin_station_id,
            dropoff_destination_id=request_row.destination_id,
            verification_code=self._codes.generate(),
        )
        booking.transition_to(BookingStatus.CONFIRMED, at=now)
        # The driver is already agreed -- that is what accepting the offer
        # meant -- so the booking says so rather than showing "awaiting driver".
        booking.transition_to(BookingStatus.DRIVER_ASSIGNED, at=now)
        booking_row = self._bookings.create(
            id=booking.id,
            number=booking.number,
            trip_id=trip.id,
            passenger_id=cmd.passenger_id,
            ride_kind=booking.ride_kind.value,
            seat_count=booking.seat_count,
            pickup_sequence=0,
            dropoff_sequence=1,
            pickup_station_id=request_row.origin_station_id,
            dropoff_destination_id=request_row.destination_id,
            fare_total_minor=agreed.amount_minor,
            fare_total_currency=agreed.currency,
            fare_breakdown=list(booking.fare_breakdown),
            status=booking.status.value,
            verification_code=booking.verification_code,
            confirmed_at=now,
        )
        self._bookings.session.flush()

        self._seats.reserve(taken, booking_row.id)

        request_row.status = RideRequestStatus.MATCHED.value
        request_row.trip_id = trip.id
        request_row.agreed_fare_minor = agreed.amount_minor
        request_row.accepted_offer_id = offer_row.id
        request_row.version += 1
        self._requests.save(request_row)

        offer_row.status = offer.status.value
        offer_row.responded_at = now
        offer_row.version += 1
        self._offers.save(offer_row)
        # Every other driver is told at once rather than left refreshing a
        # request that is already taken.
        # Read who is losing *before* declining them, and keep the ids rather
        # than the rows: the UPDATE expires those objects, so re-reading their
        # status afterwards finds DECLINED and matches nobody.
        losing_driver_ids = {
            o.driver_id
            for o in self._offers.for_request(request_row.id)
            if o.id != offer_row.id and o.status == FareOfferStatus.OFFERED.value
        }
        self._offers.decline_others(request_id=request_row.id, except_id=offer_row.id, at=now)

        # The chosen driver is on their way to a passenger, so they are told
        # first and by name.
        _tell(
            self._notifier,
            user_id=driver.user_id,
            message_key="notify.offer.accepted",
            payload={
                "trip_id": trip.id,
                "booking_number": booking_row.number,
                "amount_minor": agreed.amount_minor,
                "currency": agreed.currency,
            },
            trip_id=trip.id,
            booking_id=booking_row.id,
        )
        # And everyone else, so nobody drives to a station where the passenger
        # has already gone.
        for other in self._drivers.by_ids(losing_driver_ids):
            _tell(
                self._notifier,
                user_id=other.user_id,
                message_key="notify.offer.declined",
                payload={"ride_request_id": request_row.id},
            )

        self._audit.write(
            "fare_offer.accepted",
            actor_id=cmd.passenger_id,
            actor_role=ActorRole.PASSENGER,
            entity_type="fare_offer",
            entity_id=offer_row.id,
            after={
                "trip_id": trip.id,
                "booking_id": booking_row.id,
                "agreed_minor": agreed.amount_minor,
                "currency": agreed.currency,
                "driver_id": driver.id,
            },
            request_id=cmd.request_id,
        )
        return AcceptOfferResult(
            ride_request_id=request_row.id,
            offer_id=offer_row.id,
            trip_id=trip.id,
            trip_number=trip.number,
            booking_id=booking_row.id,
            booking_number=booking_row.number,
            verification_code=booking_row.verification_code,
            driver_id=driver.id,
            agreed_fare=agreed,
        )
