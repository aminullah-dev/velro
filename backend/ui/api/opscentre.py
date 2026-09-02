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

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from domain.enums import (
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
    VehicleStatus,
)
from domain.identity import PASSENGER
from domain.lifecycles import BOOKABLE_TRIP_STATUSES
from infrastructure.db.models.geography import StationRow, VillageRow
from infrastructure.db.models.identity import RoleRow, UserRoleRow
from infrastructure.db.models.money import CommissionRow, SettlementRow, WalletRow
from infrastructure.db.models.ops import CancellationRow, SupportTicketRow
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


def business_day(now: datetime) -> tuple[datetime, datetime]:
    local = now.astimezone(KABUL)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


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
        DriverRow.availability.in_(
            (DriverAvailability.ONLINE.value, DriverAvailability.ON_TRIP.value)
        ),
        or_(
            DriverLocationRow.recorded_at.is_(None),
            DriverLocationRow.recorded_at < now - stale_after,
        ),
    ]


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
    open_request = (
        RideRequestRow.status == RideRequestStatus.OPEN.value,
        RideRequestRow.expires_at > now,
    )
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
    }
