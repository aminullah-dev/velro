"""ORM models.

These map to domain entities; they are never returned above the infrastructure
layer and never used as API schemas. Three shapes, three purposes: wire
(Pydantic), business (domain dataclasses), storage (these).
"""

from infrastructure.db.models.geography import (  # noqa: F401
    DestinationRow,
    DistrictRow,
    ProvinceRow,
    RegionRow,
    StationRow,
    VillageAliasRow,
    VillageRow,
)
from infrastructure.db.models.identity import (  # noqa: F401
    OtpChallengeRow,
    PermissionRow,
    RefreshTokenRow,
    RolePermissionRow,
    RoleRow,
    UserRoleRow,
    UserRow,
)
from infrastructure.db.models.money import (  # noqa: F401
    CommissionRow,
    PaymentRow,
    SettlementRow,
    WalletRow,
    WalletTransactionRow,
)
from infrastructure.db.models.ops import (  # noqa: F401
    AuditLogRow,
    CancellationRow,
    DeviceTokenRow,
    IdempotencyRow,
    ImportJobRow,
    NotificationRow,
    NumberSequenceRow,
    RatingRow,
    SettingRow,
    SupportTicketRow,
    TicketMessageRow,
)
from infrastructure.db.models.routing import (  # noqa: F401
    FareRuleRow,
    RouteRow,
    RouteScheduleRow,
    RouteStopRow,
    RouteTemplateRow,
    VehicleTypeRow,
)
from infrastructure.db.models.supply import (  # noqa: F401
    DriverDocumentRow,
    DriverLocationRow,
    DriverRow,
    VehicleRow,
)
from infrastructure.db.models.trips import (  # noqa: F401
    BookingRow,
    BookingSeatRow,
    DispatchOfferRow,
    RideRequestRow,
    TripRow,
    TripSeatRow,
    TripStopRow,
)
