package af.velro.domain

/**
 * A transition table with teeth.
 *
 * The app mirrors the server's lifecycles so a screen can grey out an action
 * that would be refused, rather than letting a driver tap it on a bad
 * connection and wait for a 409. The server remains authoritative: this is an
 * optimistic check, never a substitute for one.
 */
class StateMachine<S : Enum<S>>(
    private val transitions: Map<S, Set<S>>,
    val errorCode: String,
) {
    fun allowedFrom(current: S): Set<S> = transitions[current].orEmpty()

    fun can(current: S, target: S): Boolean = target in allowedFrom(current)

    fun isTerminal(state: S): Boolean = allowedFrom(state).isEmpty()

    val terminalStates: Set<S> get() = transitions.filterValues { it.isEmpty() }.keys

    /**
     * The shortest declared route from one state to another.
     *
     * Used when something following another entity's lifecycle has missed an
     * intermediate step: a booking at CONFIRMED whose trip already reached
     * ARRIVED_AT_PICKUP must pass through DRIVER_ASSIGNED rather than being
     * stranded or teleported. Returns null when no legal route exists.
     */
    fun path(current: S, target: S): List<S>? {
        if (current == target) return emptyList()
        val seen = mutableSetOf(current)
        val queue = ArrayDeque<Pair<S, List<S>>>()
        queue.add(current to emptyList())
        while (queue.isNotEmpty()) {
            val (state, route) = queue.removeFirst()
            for (next in allowedFrom(state).sortedBy { it.name }) {
                if (next in seen) continue
                val extended = route + next
                if (next == target) return extended
                seen.add(next)
                queue.add(next to extended)
            }
        }
        return null
    }
}

object Lifecycles {
    val trip = StateMachine(
        mapOf(
            TripStatus.SCHEDULED to setOf(
                TripStatus.DRIVER_ASSIGNED, TripStatus.CANCELLED, TripStatus.EXPIRED,
            ),
            TripStatus.REQUESTED to setOf(
                TripStatus.DRIVER_ASSIGNED, TripStatus.NO_DRIVER_AVAILABLE,
                TripStatus.CANCELLED, TripStatus.EXPIRED,
            ),
            TripStatus.DRIVER_ASSIGNED to setOf(
                TripStatus.DRIVER_ARRIVING, TripStatus.REQUESTED,
                TripStatus.SCHEDULED, TripStatus.CANCELLED,
            ),
            TripStatus.DRIVER_ARRIVING to setOf(
                TripStatus.ARRIVED_AT_PICKUP, TripStatus.REQUESTED, TripStatus.CANCELLED,
            ),
            TripStatus.ARRIVED_AT_PICKUP to setOf(TripStatus.BOARDING, TripStatus.CANCELLED),
            TripStatus.BOARDING to setOf(TripStatus.IN_TRANSIT, TripStatus.CANCELLED),
            // No cancellation once the vehicle is moving: an interrupted journey
            // is an incident with its own record, not a status change.
            TripStatus.IN_TRANSIT to setOf(TripStatus.ARRIVED),
            TripStatus.ARRIVED to setOf(TripStatus.COMPLETED),
            TripStatus.COMPLETED to emptySet(),
            TripStatus.CANCELLED to emptySet(),
            TripStatus.EXPIRED to emptySet(),
            TripStatus.NO_DRIVER_AVAILABLE to emptySet(),
        ),
        errorCode = "TRIP_INVALID_TRANSITION",
    )

    val booking = StateMachine(
        mapOf(
            BookingStatus.PENDING to setOf(BookingStatus.CONFIRMED, BookingStatus.CANCELLED),
            BookingStatus.CONFIRMED to setOf(
                BookingStatus.DRIVER_ASSIGNED, BookingStatus.CANCELLED,
            ),
            BookingStatus.DRIVER_ASSIGNED to setOf(
                BookingStatus.READY, BookingStatus.CONFIRMED, BookingStatus.CANCELLED,
            ),
            BookingStatus.READY to setOf(
                BookingStatus.ONBOARD, BookingStatus.CANCELLED, BookingStatus.NO_SHOW,
            ),
            BookingStatus.ONBOARD to setOf(BookingStatus.COMPLETED),
            BookingStatus.COMPLETED to emptySet(),
            BookingStatus.CANCELLED to emptySet(),
            BookingStatus.NO_SHOW to emptySet(),
        ),
        errorCode = "BOOKING_INVALID_TRANSITION",
    )

    val settlement = StateMachine(
        mapOf(
            SettlementStatus.PENDING to setOf(
                SettlementStatus.PROCESSING, SettlementStatus.REJECTED,
            ),
            SettlementStatus.PROCESSING to setOf(
                SettlementStatus.PAID, SettlementStatus.REJECTED,
            ),
            SettlementStatus.PAID to emptySet(),
            SettlementStatus.REJECTED to emptySet(),
        ),
        errorCode = "SETTLEMENT_INVALID_TRANSITION",
    )

    /** Statuses in which a trip still accepts new seat bookings. */
    val bookableTripStatuses = setOf(
        TripStatus.SCHEDULED,
        TripStatus.DRIVER_ASSIGNED,
        TripStatus.DRIVER_ARRIVING,
        TripStatus.ARRIVED_AT_PICKUP,
    )

    /** Statuses from which a passenger may still cancel. */
    val cancellableBookingStatuses = setOf(
        BookingStatus.PENDING,
        BookingStatus.CONFIRMED,
        BookingStatus.DRIVER_ASSIGNED,
        BookingStatus.READY,
    )

    /** When a trip advances, the bookings riding on it advance to these. */
    val tripToBooking = mapOf(
        TripStatus.DRIVER_ASSIGNED to BookingStatus.DRIVER_ASSIGNED,
        TripStatus.ARRIVED_AT_PICKUP to BookingStatus.READY,
        TripStatus.IN_TRANSIT to BookingStatus.ONBOARD,
        TripStatus.COMPLETED to BookingStatus.COMPLETED,
        // The three ways a trip ends without anybody travelling. A booking left
        // at DRIVER_ASSIGNED or READY is a passenger holding a boarding code,
        // waiting at a roadside for a vehicle nobody is driving.
        //
        // ONBOARD is not caught by this: BOOKING has no ONBOARD -> CANCELLED
        // edge, so followTrip leaves those alone. Once someone is in the car
        // the journey happened, whatever later becomes of the trip record.
        TripStatus.CANCELLED to BookingStatus.CANCELLED,
        TripStatus.EXPIRED to BookingStatus.CANCELLED,
        TripStatus.NO_DRIVER_AVAILABLE to BookingStatus.CANCELLED,
    )
}
