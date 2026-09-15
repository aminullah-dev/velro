"""What is happening on the network right now.

The dashboard used to be fourteen counters. An operator could read that
eleven trips existed today and that two drivers were online, and could not
tell from any of it whether somebody was about to be left at a roadside.
This module answers the four questions a person leaving the screen open all
day actually has: what is happening now, what needs me, what is about to go
wrong, and how did today go -- and every number that means "act" is one the
panel can turn into the filtered list behind it.

Everything is an aggregate computed in the database. About thirty small
counts, each against an indexed column, for a screen refreshed every half
minute by at most a handful of people; the tables they read are the ones
that grow fastest, which is why none of them fetches rows to count them in
Python.

The clauses that define "needs a driver", "overdue" and "no GPS fix" live
here and nowhere else: the Trips and Drivers lists filter by the same
functions, so the number on a card and the rows behind it can never
disagree.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Date, and_, case, cast, exists, func, or_, select
from sqlalchemy.orm import Session

from domain.enums import (
    BookingStatus,
    DocumentStatus,
    DriverApprovalStatus,
    DriverAvailability,
    FareOfferStatus,
    RideRequestStatus,
    RouteStatus,
    SeatStatus,
    SettlementStatus,
    TicketStatus,
    TripStatus,
    UserStatus,
    VehicleStatus,
)
from domain.identity import DRIVER as DRIVER_ROLE
from domain.identity import PASSENGER, STAFF_ROLES
from domain.lifecycles import BOOKABLE_TRIP_STATUSES
from infrastructure.db.models.geography import StationRow, VillageRow
from infrastructure.db.models.identity import RoleRow, UserRoleRow, UserRow
from infrastructure.db.models.money import CommissionRow, SettlementRow, WalletRow
from infrastructure.db.models.ops import AppVersionCheckRow, CancellationRow, SupportTicketRow
from infrastructure.db.models.routing import RouteRow
from infrastructure.db.models.supply import (
    DriverDocumentRow,
    DriverLocationRow,
    DriverRow,
    VehicleDocumentRow,
    VehicleRow,
)
from infrastructure.db.models.trips import (
    BookingRow,
    FareOfferRow,
    RideRequestRow,
    TripRow,
    TripSeatRow,
)
from infrastructure.db.repositories.supply import VehicleRepository
from infrastructure.db.repositories.trips import TripRepository
from ui.api import release_manifest

# A "day" is a business day in the product's timezone, not date() in UTC.
KABUL = ZoneInfo("Asia/Kabul")

ON_THE_WAY = (TripStatus.DRIVER_ASSIGNED.value, TripStatus.DRIVER_ARRIVING.value)
AT_THE_STATION = (TripStatus.ARRIVED_AT_PICKUP.value, TripStatus.BOARDING.value)
MOVING = (TripStatus.IN_TRANSIT.value, TripStatus.ARRIVED.value)
NEEDS_DRIVER = (TripStatus.SCHEDULED.value, TripStatus.REQUESTED.value)
NOT_TRAVELLING = (
    TripStatus.CANCELLED.value, TripStatus.EXPIRED.value, TripStatus.NO_DRIVER_AVAILABLE.value,
)
BOOKABLE = tuple(s.value for s in BOOKABLE_TRIP_STATUSES)
#: A driver somebody could be looking for on a map.
WORKING = (DriverAvailability.ONLINE.value, DriverAvailability.ON_TRIP.value)
#: A trip with a driver on it that has not finished, in the order it moves
#: through them -- later in this tuple is further along the road.
UNDERWAY = (*ON_THE_WAY, *AT_THE_STATION, *MOVING)

#: A trip still waiting for a driver this long after it should have left is
#: still somebody's journey, not yet a record. Past this the board stops
#: showing it and the dashboard starts counting it as overdue.
OVERDUE_GRACE = timedelta(minutes=30)
#: What "departing soon" means on the live panel.
DEPARTING_SOON = timedelta(hours=2)
#: A vehicle leaving within this window with nobody booked is a departure
#: the office might want to know about before the driver does.
EMPTY_DEPARTURE_WINDOW = timedelta(hours=3)
#: How far ahead the capacity figures look.
CAPACITY_HORIZON = timedelta(hours=24)
#: A permit running out within this long is worth a phone call now.
EXPIRING_WITHIN = timedelta(days=30)
#: A trip with this share of its seats or fewer left is "nearly full".
NEARLY_FULL_FRACTION = 0.2
#: The history strip under "how did today go": this many business days,
#: today last. A week is what an operator compares today against -- "is this
#: Thursday normal" -- and seven bars still fit on a laptop without scrolling.
HISTORY_DAYS = 7
#: How far back the app-version counts are summed. The same week, so an old
#: build that stopped launching a fortnight ago has dropped off the list.
APP_VERSION_WINDOW_DAYS = 7
#: How many builds the dashboard lists, most launched first. The counter is
#: fed by an unauthenticated endpoint; a script inventing version codes must
#: not be able to push the real builds off the panel or grow its answer.
APP_VERSIONS_SHOWN = 40
#: The passenger card's two windows, in business days ending today. The
#: week is the history strip's week, so its bars add up to new_7d.
PASSENGER_WEEK_DAYS = 7
PASSENGER_MONTH_DAYS = 30


def business_day(now: datetime) -> tuple[datetime, datetime]:
    local = now.astimezone(KABUL)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def kabul_date(column):
    """The business day a timestamptz column falls on, decided by the database.

    timezone('Asia/Kabul', ts) is the wall-clock time in Kabul, whatever the
    session's own TimeZone happens to be, and its date is the day an operator
    in Charikar would say it happened on. date(ts) would be the day in UTC --
    wrong for every event between midnight and half past four in the morning.
    The zone is KABUL's own key, so business_day() and this cannot drift apart.
    """
    return cast(func.timezone(KABUL.key, column), Date)


# -- the shared clauses -----------------------------------------------------

def needs_driver_clause(now: datetime, *, horizon: timedelta | None = None):
    """A trip with nobody to drive it that is still worth driving."""
    clauses = [
        TripRow.driver_id.is_(None),
        TripRow.status.in_(NEEDS_DRIVER),
        TripRow.scheduled_departure_at >= now - OVERDUE_GRACE,
    ]
    if horizon is not None:
        clauses.append(TripRow.scheduled_departure_at <= now + horizon)
    return clauses


def overdue_clause(now: datetime):
    """A trip whose time has passed with nobody moving it along.

    SCHEDULED or REQUESTED past its grace is a journey that never happened
    and was never called off; DRIVER_ASSIGNED past it is a driver who was
    given a trip and has not touched his phone since.
    """
    return [
        TripRow.status.in_((*NEEDS_DRIVER, TripStatus.DRIVER_ASSIGNED.value)),
        TripRow.scheduled_departure_at < now - OVERDUE_GRACE,
    ]


def stale_gps_clause(now: datetime, stale_after: timedelta):
    """A working driver the office cannot place. Needs DriverLocationRow
    outer-joined on driver_id."""
    return [
        DriverRow.availability.in_(WORKING),
        or_(
            DriverLocationRow.recorded_at.is_(None),
            DriverLocationRow.recorded_at < now - stale_after,
        ),
    ]


def open_request_clause(now: datetime) -> tuple[Any, ...]:
    """A ride request a driver can still answer: open, and not yet run out."""
    return (
        RideRequestRow.status == RideRequestStatus.OPEN.value,
        RideRequestRow.expires_at > now,
    )


def holds_role_clause(codes: frozenset[str] | set[str]) -> Any:
    """A user who holds any of these roles now. Correlates on UserRow.id.

    A grant is a row that can be revoked, and so is a role; both are read,
    the same rule UserRepository.roles_of applies. A user can hold several
    roles -- every sign-up is a passenger, and a driver stays one -- so this
    asks "has this role", never "is only this".
    """
    return exists(
        select(UserRoleRow.id)
        .join(RoleRow, RoleRow.id == UserRoleRow.role_id)
        .where(
            UserRoleRow.user_id == UserRow.id,
            UserRoleRow.deleted_at.is_(None),
            RoleRow.deleted_at.is_(None),
            RoleRow.code.in_(sorted(codes)),
        )
    )


#: Roles that make an account something more than a passenger.
_BEYOND_PASSENGER = frozenset({DRIVER_ROLE, *STAFF_ROLES})


def passenger_only_clause() -> Any:
    """An account that is a passenger and nothing else. Correlates on UserRow.id.

    Every sign-up is granted PASSENGER, and a driver or a member of staff
    only ever gains roles on top of it -- so "holds PASSENGER" is everybody.
    This is what the Passengers screens mean: PASSENGER, and neither DRIVER
    nor any staff role. Decided by roles alone, as they are now: registering
    as a driver grants DRIVER at once, so an applicant still waiting for
    approval is already not a passenger here.
    """
    return and_(
        holds_role_clause({PASSENGER}),
        ~holds_role_clause(_BEYOND_PASSENGER),
    )


# -- the snapshot -----------------------------------------------------------

def snapshot(session: Session, settings: Any, now: datetime) -> dict[str, Any]:
    start, end = business_day(now)
    today: date = start.date()
    at_risk_within = timedelta(minutes=settings.get_int("dispatch.at_risk_minutes", 60))
    stale_after = timedelta(seconds=settings.get_int("dispatch.stale_gps_seconds", 300))
    unanswered_after = timedelta(
        minutes=settings.get_int("dispatch.unanswered_after_minutes", 10)
    )

    def count(model, *where) -> int:
        stmt = select(func.count()).select_from(model).where(model.deleted_at.is_(None), *where)
        return int(session.scalar(stmt) or 0)

    def total(column, *where) -> int:
        return int(session.scalar(select(func.coalesce(func.sum(column), 0)).where(*where)) or 0)

    trips_today = (
        TripRow.scheduled_departure_at >= start,
        TripRow.scheduled_departure_at < end,
    )
    settled_today = (
        CommissionRow.created_at >= start,
        CommissionRow.created_at < end,
        CommissionRow.deleted_at.is_(None),
    )

    # -- live ----------------------------------------------------------------
    live = {
        "on_the_way": count(TripRow, TripRow.status.in_(ON_THE_WAY)),
        "at_the_station": count(TripRow, TripRow.status.in_(AT_THE_STATION)),
        "moving": count(TripRow, TripRow.status.in_(MOVING)),
        "departing_soon": count(
            TripRow,
            TripRow.status.in_((*NEEDS_DRIVER, *ON_THE_WAY)),
            TripRow.scheduled_departure_at >= now,
            TripRow.scheduled_departure_at <= now + DEPARTING_SOON,
        ),
    }

    # -- attention -----------------------------------------------------------
    open_request = open_request_clause(now)
    has_offer = exists(
        select(FareOfferRow.id).where(
            FareOfferRow.ride_request_id == RideRequestRow.id,
            FareOfferRow.status == FareOfferStatus.OFFERED.value,
            FareOfferRow.deleted_at.is_(None),
        )
    )
    stale_gps = int(
        session.scalar(
            select(func.count())
            .select_from(DriverRow)
            .outerjoin(DriverLocationRow, DriverLocationRow.driver_id == DriverRow.id)
            .where(DriverRow.deleted_at.is_(None), *stale_gps_clause(now, stale_after))
        )
        or 0
    )
    expiring_soon = today + EXPIRING_WITHIN
    attention = {
        "unassigned_trips": count(TripRow, *needs_driver_clause(now)),
        "departures_at_risk": count(
            TripRow, *needs_driver_clause(now, horizon=at_risk_within)
        ),
        "overdue_trips": count(TripRow, *overdue_clause(now)),
        "open_requests": count(RideRequestRow, *open_request),
        "unanswered_requests": count(
            RideRequestRow,
            *open_request,
            RideRequestRow.created_at <= now - unanswered_after,
            ~has_offer,
        ),
        "pending_drivers": count(
            DriverRow, DriverRow.approval_status == DriverApprovalStatus.PENDING.value
        ),
        "pending_vehicles": count(VehicleRow, VehicleRow.status == VehicleStatus.PENDING.value),
        "pending_documents": (
            count(DriverDocumentRow, DriverDocumentRow.status == DocumentStatus.PENDING.value)
            + count(
                VehicleDocumentRow, VehicleDocumentRow.status == DocumentStatus.PENDING.value
            )
        ),
        "expiring_documents": (
            count(
                DriverDocumentRow,
                DriverDocumentRow.status == DocumentStatus.VERIFIED.value,
                DriverDocumentRow.expires_on.is_not(None),
                DriverDocumentRow.expires_on >= today,
                DriverDocumentRow.expires_on <= expiring_soon,
            )
            + count(
                VehicleDocumentRow,
                VehicleDocumentRow.status == DocumentStatus.VERIFIED.value,
                VehicleDocumentRow.expires_on.is_not(None),
                VehicleDocumentRow.expires_on >= today,
                VehicleDocumentRow.expires_on <= expiring_soon,
            )
        ),
        "open_tickets": count(
            SupportTicketRow,
            SupportTicketRow.status.in_(
                (TicketStatus.OPEN.value, TicketStatus.IN_PROGRESS.value)
            ),
        ),
        "stale_gps_drivers": stale_gps,
    }

    # -- today ---------------------------------------------------------------
    capacity_today = total(
        TripRow.seat_capacity,
        *trips_today,
        TripRow.status.not_in(NOT_TRAVELLING),
        TripRow.deleted_at.is_(None),
    )
    sold_today = int(
        session.scalar(
            select(func.count())
            .select_from(TripSeatRow)
            .join(TripRow, TripRow.id == TripSeatRow.trip_id)
            .where(
                *trips_today,
                TripRow.status.not_in(NOT_TRAVELLING),
                TripRow.deleted_at.is_(None),
                TripSeatRow.deleted_at.is_(None),
                TripSeatRow.status.in_(
                    (SeatStatus.RESERVED.value, SeatStatus.OCCUPIED.value)
                ),
            )
        )
        or 0
    )
    today_section = {
        "trips": count(TripRow, *trips_today),
        "bookings": count(BookingRow, BookingRow.created_at >= start, BookingRow.created_at < end),
        "completed_trips": count(
            TripRow,
            TripRow.status == TripStatus.COMPLETED.value,
            TripRow.completed_at >= start,
            TripRow.completed_at < end,
        ),
        "cancellations": count(
            CancellationRow, CancellationRow.created_at >= start, CancellationRow.created_at < end
        ),
        "seats_capacity": capacity_today,
        "seats_sold": sold_today,
        "utilisation_percent": (
            round(100 * sold_today / capacity_today) if capacity_today else None
        ),
    }

    # -- capacity ahead ------------------------------------------------------
    upcoming = session.execute(
        select(TripRow.id, TripRow.seat_capacity, TripRow.scheduled_departure_at).where(
            TripRow.deleted_at.is_(None),
            TripRow.status.in_(BOOKABLE),
            TripRow.scheduled_departure_at >= now,
            TripRow.scheduled_departure_at <= now + CAPACITY_HORIZON,
        )
    ).all()
    free_by_trip: dict[str, int] = {}
    if upcoming:
        free_by_trip = {
            trip_id: int(n)
            for trip_id, n in session.execute(
                select(TripSeatRow.trip_id, func.count())
                .where(
                    TripSeatRow.trip_id.in_([t.id for t in upcoming]),
                    TripSeatRow.status == SeatStatus.AVAILABLE.value,
                    TripSeatRow.booking_id.is_(None),
                    TripSeatRow.deleted_at.is_(None),
                )
                .group_by(TripSeatRow.trip_id)
            ).all()
        }
    nearly_full = empty_soon = 0
    for trip_id, capacity, departure in upcoming:
        free = free_by_trip.get(trip_id, 0)
        if free <= capacity * NEARLY_FULL_FRACTION:
            nearly_full += 1
        if free == capacity and departure <= now + EMPTY_DEPARTURE_WINDOW:
            empty_soon += 1
    capacity = {
        "upcoming_trips": len(upcoming),
        "nearly_full_trips": nearly_full,
        "empty_departures": empty_soon,
    }

    # -- drivers -------------------------------------------------------------
    drivers = {
        "online": count(DriverRow, DriverRow.availability == DriverAvailability.ONLINE.value),
        "on_trip": count(DriverRow, DriverRow.availability == DriverAvailability.ON_TRIP.value),
        "offline": count(
            DriverRow,
            DriverRow.approval_status == DriverApprovalStatus.APPROVED.value,
            DriverRow.availability == DriverAvailability.OFFLINE.value,
        ),
        "pending": attention["pending_drivers"],
        "suspended": count(
            DriverRow, DriverRow.approval_status == DriverApprovalStatus.SUSPENDED.value
        ),
        "total": count(DriverRow),
        "without_fix": stale_gps,
    }

    # -- money ---------------------------------------------------------------
    finance = {
        "currency": "AFN",
        "revenue_today_minor": total(CommissionRow.gross_minor, *settled_today),
        "commission_today_minor": total(CommissionRow.platform_minor, *settled_today),
        "driver_earnings_today_minor": total(CommissionRow.driver_minor, *settled_today),
        # Cash fares: drivers hold VELRO's share until they hand it in.
        "cash_owed_minor": -total(
            WalletRow.available_minor,
            WalletRow.available_minor < 0,
            WalletRow.deleted_at.is_(None),
        ),
        "payouts_due_minor": total(
            WalletRow.available_minor,
            WalletRow.available_minor > 0,
            WalletRow.deleted_at.is_(None),
        ),
        "settlements_open": count(
            SettlementRow,
            SettlementRow.status.in_(
                (SettlementStatus.PENDING.value, SettlementStatus.PROCESSING.value)
            ),
        ),
    }

    # -- the network ---------------------------------------------------------
    active_route = (RouteRow.status == RouteStatus.ACTIVE.value, RouteRow.deleted_at.is_(None))
    has_station = exists(
        select(StationRow.id).where(
            StationRow.village_id == VillageRow.id, StationRow.deleted_at.is_(None)
        )
    )
    has_route = exists(
        select(RouteRow.id).where(RouteRow.origin_station_id == StationRow.id, *active_route)
    )
    has_upcoming_trip = exists(
        select(TripRow.id).where(
            TripRow.route_id == RouteRow.id,
            TripRow.deleted_at.is_(None),
            TripRow.status.in_(BOOKABLE),
            TripRow.scheduled_departure_at >= now,
        )
    )
    network = {
        "routes_active": count(RouteRow, active_route[0]),
        "stations": count(StationRow),
        "villages": count(VillageRow),
        "villages_without_coordinates": count(VillageRow, VillageRow.latitude.is_(None)),
        "villages_without_stations": count(VillageRow, ~has_station),
        "stations_without_routes": count(StationRow, ~has_route),
        "routes_without_upcoming_trips": count(RouteRow, active_route[0], ~has_upcoming_trip),
    }

    # -- people --------------------------------------------------------------
    passengers = int(
        session.scalar(
            select(func.count(func.distinct(UserRoleRow.user_id)))
            .join(RoleRow, RoleRow.id == UserRoleRow.role_id)
            .where(RoleRow.code == PASSENGER, UserRoleRow.deleted_at.is_(None))
        )
        or 0
    )

    return {
        "generated_at": now,
        "live": live,
        "attention": attention,
        "today": today_section,
        "capacity": capacity,
        "drivers": drivers,
        "finance": finance,
        "network": network,
        "people": {"passengers": passengers, "drivers": drivers["total"]},
        "passengers": _passengers(session, now, start),
        "history": _history(session, today, end),
        "apps": _apps(session, today),
    }


# -- the people VELRO exists for ---------------------------------------------

def _passengers(session: Session, now: datetime, start: datetime) -> dict[str, int]:
    """Who the passengers are, beyond one number.

    A passenger is an account that still exists and is a passenger only --
    PASSENGER with no driver or staff role on top (passenger_only_clause),
    the same set GET /admin/users?passenger_only=true lists. Every figure
    below is a subset of that total, so no card can read larger than the
    one it sits beside. (people.passengers above is the
    older, looser count -- role grants, deleted accounts included -- and is
    left exactly as it was for the screens already reading it.)

    The windows are business days in Kabul ending today, like everything
    else here: "the last 7 days" is today and the six before it.
    """
    person = (UserRow.deleted_at.is_(None), passenger_only_clause())

    def people(*where: Any) -> int:
        stmt = select(func.count()).select_from(UserRow).where(*person, *where)
        return int(session.scalar(stmt) or 0)

    week = start - timedelta(days=PASSENGER_WEEK_DAYS - 1)
    month = start - timedelta(days=PASSENGER_MONTH_DAYS - 1)

    def active_since(since: datetime) -> Any:
        booked = select(BookingRow.passenger_id).where(
            BookingRow.created_at >= since, BookingRow.deleted_at.is_(None)
        )
        asked = select(RideRequestRow.passenger_id).where(
            RideRequestRow.created_at >= since, RideRequestRow.deleted_at.is_(None)
        )
        return or_(UserRow.id.in_(booked), UserRow.id.in_(asked))

    # A booking completes after it is made; the trip is what happened in the
    # window, so it is dated by completion where there is one.
    repeat = (
        select(BookingRow.passenger_id)
        .where(
            BookingRow.status == BookingStatus.COMPLETED.value,
            BookingRow.deleted_at.is_(None),
            func.coalesce(BookingRow.completed_at, BookingRow.created_at) >= month,
        )
        .group_by(BookingRow.passenger_id)
        .having(func.count() >= 2)
    )
    waiting = select(RideRequestRow.passenger_id).where(
        *open_request_clause(now), RideRequestRow.deleted_at.is_(None)
    )
    return {
        "total": people(),
        "new_today": people(UserRow.created_at >= start),
        "new_7d": people(UserRow.created_at >= week),
        "active_7d": people(active_since(week)),
        "active_30d": people(active_since(month)),
        "repeat_30d": people(UserRow.id.in_(repeat)),
        "suspended": people(UserRow.status == UserStatus.SUSPENDED.value),
        "with_open_request": people(UserRow.id.in_(waiting)),
    }


# -- the week behind today --------------------------------------------------

def _history(session: Session, today: date, end: datetime) -> dict[str, Any]:
    """The last HISTORY_DAYS business days, oldest first, today last.

    Every figure has exactly the definition its counterpart in the today and
    finance sections has -- same column, same status, same deleted_at rule --
    so the last bar and the cards above it are one number, not two numbers
    that usually agree. What changes is only the grouping: one GROUP BY over
    the Kabul date per figure, five queries for the whole week rather than
    one per figure per day. A day nothing happened on is not missing, it is
    zero, and it is filled in here rather than left for the chart to guess.
    """
    since = end - timedelta(days=HISTORY_DAYS)
    first = today - timedelta(days=HISTORY_DAYS - 1)
    blank = {
        "trips": 0, "bookings": 0, "completed_trips": 0, "cancellations": 0,
        "revenue_minor": 0, "commission_minor": 0,
        "new_passengers": 0, "new_drivers": 0,
    }
    days: dict[date, dict[str, int]] = {
        first + timedelta(days=i): dict(blank) for i in range(HISTORY_DAYS)
    }

    def per_day(field: str, column, *where) -> None:
        day = kabul_date(column)
        stmt = (
            select(day, func.count())
            .where(column >= since, column < end, *where)
            .group_by(day)
        )
        for when, n in session.execute(stmt).all():
            if when in days:
                days[when][field] = int(n)

    per_day("trips", TripRow.scheduled_departure_at, TripRow.deleted_at.is_(None))
    per_day("bookings", BookingRow.created_at, BookingRow.deleted_at.is_(None))
    per_day(
        "completed_trips",
        TripRow.completed_at,
        TripRow.status == TripStatus.COMPLETED.value,
        TripRow.deleted_at.is_(None),
    )
    per_day("cancellations", CancellationRow.created_at, CancellationRow.deleted_at.is_(None))
    # Sign-ups, by the passenger card's definition and the drivers card's:
    # a passenger-only account, and a driver record. Roles are read as they
    # are now, so a passenger approved to drive later leaves his sign-up day's
    # bar -- the price of the bars adding up to the card's new_7d.
    per_day(
        "new_passengers",
        UserRow.created_at,
        UserRow.deleted_at.is_(None),
        passenger_only_clause(),
    )
    per_day("new_drivers", DriverRow.created_at, DriverRow.deleted_at.is_(None))

    settled = kabul_date(CommissionRow.created_at)
    for when, gross, platform in session.execute(
        select(
            settled,
            func.coalesce(func.sum(CommissionRow.gross_minor), 0),
            func.coalesce(func.sum(CommissionRow.platform_minor), 0),
        )
        .where(
            CommissionRow.created_at >= since,
            CommissionRow.created_at < end,
            CommissionRow.deleted_at.is_(None),
        )
        .group_by(settled)
    ).all():
        if when in days:
            days[when]["revenue_minor"] = int(gross)
            days[when]["commission_minor"] = int(platform)

    return {
        "currency": "AFN",
        "days": [{"date": when.isoformat(), **days[when]} for when in sorted(days)],
    }


# -- the builds in people's hands -------------------------------------------

def _apps(session: Session, today: date) -> dict[str, Any]:
    """What is published beside what is actually launching.

    The newest build comes from release.json, the counts from the anonymous
    table the version check fills (routers/app_release.py). Together they
    answer the question neither answers alone: how many launches last week
    were of a build older than the one on offer.
    """
    first = today - timedelta(days=APP_VERSION_WINDOW_DAYS - 1)
    checks = AppVersionCheckRow
    rows = session.execute(
        select(
            checks.app,
            checks.platform,
            checks.version_code,
            # One name per code in practice; max() only makes the choice
            # deterministic if a hand-made request ever smuggled in another.
            func.max(checks.version_name),
            func.sum(checks.checks),
        )
        .where(checks.day >= first, checks.day <= today, checks.deleted_at.is_(None))
        .group_by(checks.app, checks.platform, checks.version_code)
        .order_by(func.sum(checks.checks).desc(), checks.version_code.desc())
        .limit(APP_VERSIONS_SHOWN)
    ).all()
    # Chosen by launches, shown by app and newest build first.
    rows = sorted(rows, key=lambda row: (row[0], -int(row[2]), row[1]))
    return {
        "window_days": APP_VERSION_WINDOW_DAYS,
        "latest": release_manifest.latest_versions(),
        "versions": [
            {
                "app": app,
                "platform": platform,
                "version_code": int(code),
                "version_name": name,
                "checks": int(n or 0),
            }
            for app, platform, code, name, n in rows
        ],
    }


# -- the live map -----------------------------------------------------------

def live_map(
    session: Session, settings: Any, now: datetime, *, rehearsing_phones: frozenset[str]
) -> dict[str, Any]:
    """Every working driver: where he is, in which car, on which trip.

    Approved drivers who are online or on a trip -- the people the office
    could send somewhere, or needs to find. A pending driver who pressed
    "online" is not on the road yet, and an offline one is at home.

    Four queries whatever the fleet: the drivers with their users and their
    one location row, their active cars, their unfinished trips, and those
    trips' place names. A query per marker is how a map on a slow connection
    becomes a blank rectangle.

    A position is marked stale by the same rule the "without a fix" card
    counts by (stale_gps_clause), so a grey pin on the map and that number
    never disagree. Rehearsing drivers -- App Review, developers, the
    accounts behind OTP_TEST_NUMBERS -- are shown, and said to be, because a
    car at a desk in Cupertino is otherwise a mystery on a map of Ghorband.
    """
    stale_after_seconds = settings.get_int("dispatch.stale_gps_seconds", 300)
    stale_before = now - timedelta(seconds=stale_after_seconds)
    on_trip_first = case(
        (DriverRow.availability == DriverAvailability.ON_TRIP.value, 0), else_=1
    )
    rows = session.execute(
        select(
            DriverRow.id,
            DriverRow.availability,
            UserRow.full_name,
            UserRow.phone,
            DriverLocationRow.latitude,
            DriverLocationRow.longitude,
            DriverLocationRow.heading_degrees,
            DriverLocationRow.recorded_at,
        )
        .join(UserRow, UserRow.id == DriverRow.user_id)
        .outerjoin(DriverLocationRow, DriverLocationRow.driver_id == DriverRow.id)
        .where(
            DriverRow.deleted_at.is_(None),
            DriverRow.approval_status == DriverApprovalStatus.APPROVED.value,
            DriverRow.availability.in_(WORKING),
        )
        .order_by(on_trip_first, UserRow.full_name.asc().nulls_last(), DriverRow.id)
    ).all()
    driver_ids = [row.id for row in rows]

    # The same car dispatch would put him in: the earliest active one.
    cars = VehicleRepository(session).active_by_driver(driver_ids)
    trips = _underway_trips(session, driver_ids)
    names = TripRepository(session).place_names([t.id for t in trips.values()])

    drivers = []
    for row in rows:
        car = cars.get(row.id)
        trip = trips.get(row.id)
        origin, destination = names.get(trip.id, (None, None)) if trip else (None, None)
        drivers.append({
            "driver_id": row.id,
            "name": row.full_name,
            "phone": row.phone,
            "availability": row.availability,
            "vehicle": (
                {"plate": car.plate_number, "brand": car.brand, "model": car.model}
                if car else None
            ),
            "location": (
                {
                    "latitude": float(row.latitude),
                    "longitude": float(row.longitude),
                    "heading_degrees": row.heading_degrees,
                    "recorded_at": row.recorded_at,
                    "stale": row.recorded_at < stale_before,
                }
                if row.recorded_at is not None else None
            ),
            "trip": (
                {
                    "id": trip.id,
                    "number": trip.number,
                    "status": trip.status,
                    "origin_name": origin,
                    "destination_name": destination,
                }
                if trip else None
            ),
            "rehearsing": row.phone is not None and row.phone in rehearsing_phones,
        })
    return {
        "generated_at": now,
        "stale_after_seconds": stale_after_seconds,
        "drivers": drivers,
    }


def _underway_trips(session: Session, driver_ids: list[str]) -> dict[str, Any]:
    """Each driver's trip in progress, one per driver.

    A driver can hold more than one unfinished trip -- this afternoon's run
    assigned while this morning's is still on the road -- and the map has
    room for one. The one furthest along wins, then the earliest departure:
    the car in transit is the trip he is driving, not the one he was given
    for later.
    """
    if not driver_ids:
        return {}
    rows = session.execute(
        select(
            TripRow.id, TripRow.driver_id, TripRow.number, TripRow.status,
            TripRow.scheduled_departure_at,
        ).where(
            TripRow.driver_id.in_(driver_ids),
            TripRow.status.in_(UNDERWAY),
            TripRow.deleted_at.is_(None),
        )
    ).all()
    chosen: dict[str, Any] = {}
    for trip in sorted(
        rows, key=lambda t: (-UNDERWAY.index(t.status), t.scheduled_departure_at, t.id)
    ):
        chosen.setdefault(trip.driver_id, trip)
    return chosen
