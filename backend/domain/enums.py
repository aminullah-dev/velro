"""Domain enumerations.

Stored as text with a CHECK constraint, never as integers: an integer status
column is unreadable in a support session and cannot be safely reordered.

These are the *lifecycle* enumerations, which are business rules and therefore
belong in code. Catalogue values an operator may extend without a deploy --
vehicle types, cancellation reasons, document types -- live in the database.
"""

from __future__ import annotations

from enum import StrEnum


class Locale(StrEnum):
    EN = "en"
    DARI = "fa-AF"
    PASHTO = "ps"


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DEACTIVATED = "DEACTIVATED"


class GeoStatus(StrEnum):
    """Shared by province, district, village, station and destination."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class DestinationKind(StrEnum):
    INTERNAL = "INTERNAL"
    EXTERNAL = "EXTERNAL"


class RouteType(StrEnum):
    LOCAL = "LOCAL"
    DISTRICT_TO_DISTRICT = "DISTRICT_TO_DISTRICT"
    INTERCITY = "INTERCITY"
    CITY = "CITY"
    STATION_TO_STATION = "STATION_TO_STATION"


class RouteStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class OriginScope(StrEnum):
    """How widely a route template applies."""

    DISTRICT = "DISTRICT"
    VILLAGE = "VILLAGE"
    STATION = "STATION"


class RideKind(StrEnum):
    PRIVATE = "PRIVATE"
    SHARED = "SHARED"


class TripStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    REQUESTED = "REQUESTED"
    DRIVER_ASSIGNED = "DRIVER_ASSIGNED"
    DRIVER_ARRIVING = "DRIVER_ARRIVING"
    ARRIVED_AT_PICKUP = "ARRIVED_AT_PICKUP"
    BOARDING = "BOARDING"
    IN_TRANSIT = "IN_TRANSIT"
    ARRIVED = "ARRIVED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    NO_DRIVER_AVAILABLE = "NO_DRIVER_AVAILABLE"


class BookingStatus(StrEnum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    DRIVER_ASSIGNED = "DRIVER_ASSIGNED"
    READY = "READY"
    ONBOARD = "ONBOARD"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    NO_SHOW = "NO_SHOW"


class SeatStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    OCCUPIED = "OCCUPIED"
    BLOCKED = "BLOCKED"


class DriverApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUSPENDED = "SUSPENDED"


class DriverAvailability(StrEnum):
    OFFLINE = "OFFLINE"
    ONLINE = "ONLINE"
    BUSY = "BUSY"
    ON_TRIP = "ON_TRIP"


class VehicleStatus(StrEnum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    RETIRED = "RETIRED"


class DocumentStatus(StrEnum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class PaymentMethod(StrEnum):
    """Only CASH is implemented. The rest exist so that adding a provider is a
    new row and a new adapter, not a schema migration."""

    CASH = "CASH"
    MOBILE_WALLET = "MOBILE_WALLET"
    CARD = "CARD"
    CORPORATE = "CORPORATE"


class PaymentStatus(StrEnum):
    PENDING = "PENDING"
    COLLECTED = "COLLECTED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class SettlementStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    PAID = "PAID"
    REJECTED = "REJECTED"


class WalletEntryKind(StrEnum):
    TRIP_EARNING = "TRIP_EARNING"
    COMMISSION = "COMMISSION"
    SETTLEMENT = "SETTLEMENT"
    ADJUSTMENT = "ADJUSTMENT"
    CANCELLATION_FEE = "CANCELLATION_FEE"


class ActorRole(StrEnum):
    PASSENGER = "PASSENGER"
    DRIVER = "DRIVER"
    DISPATCHER = "DISPATCHER"
    ADMIN = "ADMIN"
    SYSTEM = "SYSTEM"


class TicketStatus(StrEnum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class ImportStatus(StrEnum):
    UPLOADED = "UPLOADED"
    VALIDATED = "VALIDATED"
    PREVIEWED = "PREVIEWED"
    COMMITTED = "COMMITTED"
    FAILED = "FAILED"
