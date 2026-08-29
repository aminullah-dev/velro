"""The declared lifecycles.

Read this file to know what VELRO permits. Nothing else in the codebase is
allowed to have an opinion about which status follows which.
"""

from __future__ import annotations

from domain.enums import BookingStatus, SettlementStatus, TicketStatus, TripStatus
from domain.state_machine import StateMachine
from shared import error_codes

T = TripStatus
B = BookingStatus

# A trip enters either as SCHEDULED (published against a route schedule and open
# for seat booking) or as REQUESTED (an on-demand private ride awaiting
# dispatch). Both funnel into DRIVER_ASSIGNED and share the rest of the flow.
TRIP_LIFECYCLE: StateMachine[TripStatus] = StateMachine(
    {
        T.SCHEDULED: frozenset({T.DRIVER_ASSIGNED, T.CANCELLED, T.EXPIRED}),
        T.REQUESTED: frozenset(
            {T.DRIVER_ASSIGNED, T.NO_DRIVER_AVAILABLE, T.CANCELLED, T.EXPIRED}
        ),
        # Re-dispatch: a driver who cancels, or an admin override that changes
        # the driver, returns the trip to the pool rather than killing it.
        T.DRIVER_ASSIGNED: frozenset(
            {T.DRIVER_ARRIVING, T.REQUESTED, T.SCHEDULED, T.CANCELLED}
        ),
        T.DRIVER_ARRIVING: frozenset({T.ARRIVED_AT_PICKUP, T.REQUESTED, T.CANCELLED}),
        T.ARRIVED_AT_PICKUP: frozenset({T.BOARDING, T.CANCELLED}),
        T.BOARDING: frozenset({T.IN_TRANSIT, T.CANCELLED}),
        # Once the vehicle is moving there is no cancellation: an interrupted
        # journey is an incident with its own record, not a status change.
        T.IN_TRANSIT: frozenset({T.ARRIVED}),
        T.ARRIVED: frozenset({T.COMPLETED}),
        T.COMPLETED: frozenset(),
        T.CANCELLED: frozenset(),
        T.EXPIRED: frozenset(),
        T.NO_DRIVER_AVAILABLE: frozenset(),
    },
    conflict_code=error_codes.TRIP_INVALID_TRANSITION,
    entity="trip",
)

BOOKING_LIFECYCLE: StateMachine[BookingStatus] = StateMachine(
    {
        B.PENDING: frozenset({B.CONFIRMED, B.CANCELLED}),
        B.CONFIRMED: frozenset({B.DRIVER_ASSIGNED, B.CANCELLED}),
        B.DRIVER_ASSIGNED: frozenset({B.READY, B.CONFIRMED, B.CANCELLED}),
        B.READY: frozenset({B.ONBOARD, B.CANCELLED, B.NO_SHOW}),
        B.ONBOARD: frozenset({B.COMPLETED}),
        B.COMPLETED: frozenset(),
        B.CANCELLED: frozenset(),
        B.NO_SHOW: frozenset(),
    },
    conflict_code=error_codes.BOOKING_INVALID_TRANSITION,
    entity="booking",
)

# RESOLVED is deliberately not terminal. An operator marking something fixed is
# a claim; the person who raised it is the one who knows whether it was, so a
# resolved ticket can go back to IN_PROGRESS. Only CLOSED ends it.
TICKET_LIFECYCLE: StateMachine[TicketStatus] = StateMachine(
    {
        TicketStatus.OPEN: frozenset(
            {TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED, TicketStatus.CLOSED}
        ),
        TicketStatus.IN_PROGRESS: frozenset(
            {TicketStatus.RESOLVED, TicketStatus.CLOSED}
        ),
        TicketStatus.RESOLVED: frozenset(
            {TicketStatus.IN_PROGRESS, TicketStatus.CLOSED}
        ),
        TicketStatus.CLOSED: frozenset(),
    },
    conflict_code=error_codes.TICKET_INVALID_TRANSITION,
    entity="ticket",
)

SETTLEMENT_LIFECYCLE: StateMachine[SettlementStatus] = StateMachine(
    {
        SettlementStatus.PENDING: frozenset(
            {SettlementStatus.PROCESSING, SettlementStatus.REJECTED}
        ),
        SettlementStatus.PROCESSING: frozenset(
            {SettlementStatus.PAID, SettlementStatus.REJECTED}
        ),
        SettlementStatus.PAID: frozenset(),
        SettlementStatus.REJECTED: frozenset(),
    },
    conflict_code=error_codes.SETTLEMENT_INVALID_TRANSITION,
    entity="settlement",
)

# When a trip advances, the bookings riding on it advance too. A booking already
# in a terminal state (cancelled, no-show) is left alone.
TRIP_TO_BOOKING_STATUS: dict[TripStatus, BookingStatus] = {
    T.DRIVER_ASSIGNED: B.DRIVER_ASSIGNED,
    T.ARRIVED_AT_PICKUP: B.READY,
    T.IN_TRANSIT: B.ONBOARD,
    T.COMPLETED: B.COMPLETED,
    # The three ways a trip ends without travelling. A booking left at
    # DRIVER_ASSIGNED or READY is a passenger holding a boarding code, waiting
    # at a roadside for a vehicle nobody is driving.
    #
    # ONBOARD is not caught by this: BOOKING has no ONBOARD -> CANCELLED edge,
    # so follow_trip leaves those alone. Once someone is in the car the journey
    # happened, whatever later becomes of the trip record.
    T.CANCELLED: B.CANCELLED,
    T.EXPIRED: B.CANCELLED,
    T.NO_DRIVER_AVAILABLE: B.CANCELLED,
}

# Statuses in which a trip still accepts new seat bookings.
BOOKABLE_TRIP_STATUSES: frozenset[TripStatus] = frozenset(
    {T.SCHEDULED, T.DRIVER_ASSIGNED, T.DRIVER_ARRIVING, T.ARRIVED_AT_PICKUP}
)
