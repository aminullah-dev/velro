"""The composition root.

The only file where a concrete class meets an interface. Everything above it
receives what it needs; nothing above it constructs a repository, opens a
session or knows that PostgreSQL exists.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from application.pricing.fixed import FixedRouteFare
from application.use_cases.dispatch import NearestStationMatching
from domain.enums import ActorRole, UserStatus
from domain.identity import (
    ADMIN,
    DISPATCHER,
    DRIVER,
    FINANCE_MANAGER,
    OPERATIONS_MANAGER,
    PASSENGER,
    STAFF_ROLES,
    SUPER_ADMIN,
    SUPPORT_AGENT,
)
from infrastructure.db.repositories.geography import (
    DestinationRepository,
    DistrictRepository,
    GeographyRepository,
    StationRepository,
    VillageAliasRepository,
    VillageRepository,
)
from infrastructure.db.repositories.identity import (
    OtpRepository,
    RefreshTokenRepository,
    UserRepository,
)
from infrastructure.db.repositories.money import (
    CommissionRepository,
    PaymentRepository,
    SettlementRepository,
    WalletRepository,
)
from infrastructure.db.repositories.ops import (
    CancellationRepository,
    DeviceTokenRepository,
    IdempotencyRepository,
    ImportJobRepository,
    NotificationRepository,
    RatingRepository,
)
from infrastructure.db.repositories.routing import (
    FareRepository,
    RouteRepository,
    RouteScheduleRepository,
    RouteStopRepository,
    RouteTemplateRepository,
    VehicleTypeRepository,
)
from infrastructure.db.repositories.seats import TripSeatRepository
from infrastructure.db.repositories.supply import (
    DriverDocumentRepository,
    DriverLocationRepository,
    DriverRepository,
    VehicleDocumentRepository,
    VehicleRepository,
)
from infrastructure.db.repositories.support import (
    SupportTicketRepository,
    TicketMessageRepository,
)
from infrastructure.db.repositories.trips import (
    BookingRepository,
    DispatchOfferRepository,
    FareOfferRepository,
    RideRequestRepository,
    TripRepository,
)
from infrastructure.db.session import build_engine, build_session_factory
from infrastructure.services.audit import SqlAuditLog
from infrastructure.services.codes import SecretsOtpGenerator, SecretsVerificationCodeGenerator
from infrastructure.services.messaging import ConsolePushChannel, ConsoleSmsSender
from infrastructure.services.numbers import SqlNumberAllocator
from infrastructure.services.settings import SqlSettingsProvider
from infrastructure.services.sms import FallbackSmsSender, TwilioSmsSender
from infrastructure.services.storage import LocalFileStorage
from infrastructure.services.tokens import JwtTokenService
from shared import config, error_codes
from shared.clock import SystemClock
from shared.config import ConfigurationError
from shared.errors import AuthenticationError, PermissionError
from shared.ids import new_id
from ui.api.session_scope import current_session


@lru_cache(maxsize=1)
def settings() -> config.Settings:
    return config.load()


@lru_cache(maxsize=1)
def _engine():
    return build_engine(settings().database_url)


@lru_cache(maxsize=1)
def _session_factory():
    return build_session_factory(_engine())


@lru_cache(maxsize=1)
def clock() -> SystemClock:
    return SystemClock()


@lru_cache(maxsize=1)
def tokens() -> JwtTokenService:
    return JwtTokenService(settings().jwt_secret)


def db_session() -> Session:
    """The session bound to this request by ``DatabaseSessionMiddleware``.

    The commit deliberately does not happen in a dependency teardown: that runs
    after the response has been sent, so a failed commit would be invisible to
    the client. See ``ui/api/session_scope.py``.
    """
    return current_session()


SessionDep = Annotated[Session, Depends(db_session)]


# -- repositories --------------------------------------------------------

def users(session: SessionDep) -> UserRepository:
    return UserRepository(session)


def otps(session: SessionDep) -> OtpRepository:
    return OtpRepository(session)


def refresh_tokens(session: SessionDep) -> RefreshTokenRepository:
    return RefreshTokenRepository(session)


def geography(session: SessionDep) -> GeographyRepository:
    return GeographyRepository(session)


def routes(session: SessionDep) -> RouteRepository:
    return RouteRepository(session)


def route_templates(session: SessionDep) -> RouteTemplateRepository:
    return RouteTemplateRepository(session)


def route_stops(session: SessionDep) -> RouteStopRepository:
    return RouteStopRepository(session)


def fares(session: SessionDep) -> FareRepository:
    return FareRepository(session)


def trips(session: SessionDep) -> TripRepository:
    return TripRepository(session)


def seats(session: SessionDep) -> TripSeatRepository:
    return TripSeatRepository(session)


def bookings(session: SessionDep) -> BookingRepository:
    return BookingRepository(session)


def drivers(session: SessionDep) -> DriverRepository:
    return DriverRepository(session)


def vehicles(session: SessionDep) -> VehicleRepository:
    return VehicleRepository(session)


def vehicle_types(session: SessionDep) -> VehicleTypeRepository:
    return VehicleTypeRepository(session)


def driver_locations(session: SessionDep) -> DriverLocationRepository:
    return DriverLocationRepository(session)


def driver_documents(session: SessionDep) -> DriverDocumentRepository:
    return DriverDocumentRepository(session)


def vehicle_documents(session: SessionDep) -> VehicleDocumentRepository:
    return VehicleDocumentRepository(session)


@lru_cache(maxsize=1)
def file_storage() -> LocalFileStorage:
    """Files live outside anything the web server serves.

    There is no URL that reaches them; the only way out is an endpoint that
    checks who is asking.
    """
    return LocalFileStorage(settings().storage_root)


def offers(session: SessionDep) -> DispatchOfferRepository:
    return DispatchOfferRepository(session)


def payments(session: SessionDep) -> PaymentRepository:
    return PaymentRepository(session)


def commissions(session: SessionDep) -> CommissionRepository:
    return CommissionRepository(session)


def wallets(session: SessionDep) -> WalletRepository:
    return WalletRepository(session)


def settlements(session: SessionDep) -> SettlementRepository:
    return SettlementRepository(session)


def ride_requests(session: SessionDep) -> RideRequestRepository:
    return RideRequestRepository(session)


def fare_offers(session: SessionDep) -> FareOfferRepository:
    return FareOfferRepository(session)


def ratings(session: SessionDep) -> RatingRepository:
    return RatingRepository(session)


def cancellations(session: SessionDep) -> CancellationRepository:
    return CancellationRepository(session)


def device_tokens(session: SessionDep) -> DeviceTokenRepository:
    return DeviceTokenRepository(session)


def notifier(session: SessionDep):
    """Writes the notification, then tries to deliver it.

    No transport is configured yet: Firebase credentials are an environment
    concern and are not in this repository. Until they are, the row is still
    written and the message waits in the app -- which is the part that has to
    work whatever the network did.
    """
    from infrastructure.services.messaging import build_notifier

    return build_notifier(
        NotificationRepository(session), DeviceTokenRepository(session), clock()
    )


def support_tickets(session: SessionDep) -> SupportTicketRepository:
    return SupportTicketRepository(session)


def ticket_messages(session: SessionDep) -> TicketMessageRepository:
    return TicketMessageRepository(session)


def notifications(session: SessionDep) -> NotificationRepository:
    return NotificationRepository(session)


def idempotency(session: SessionDep) -> IdempotencyRepository:
    return IdempotencyRepository(session)


def import_jobs(session: SessionDep) -> ImportJobRepository:
    return ImportJobRepository(session)


def villages_repo(session: SessionDep) -> VillageRepository:
    return VillageRepository(session)


def village_aliases(session: SessionDep) -> VillageAliasRepository:
    return VillageAliasRepository(session)


def destinations_repo(session: SessionDep) -> DestinationRepository:
    return DestinationRepository(session)


def stations_repo(session: SessionDep) -> StationRepository:
    return StationRepository(session)


def districts_repo(session: SessionDep) -> DistrictRepository:
    return DistrictRepository(session)


# -- services ------------------------------------------------------------

def app_settings(session: SessionDep) -> SqlSettingsProvider:
    return SqlSettingsProvider(session)


def audit(session: SessionDep) -> SqlAuditLog:
    return SqlAuditLog(session, clock())


def numbers(session: SessionDep) -> SqlNumberAllocator:
    return SqlNumberAllocator(session)


def fare_strategy(session: SessionDep) -> FixedRouteFare:
    return FixedRouteFare(FareRepository(session))


def matching() -> NearestStationMatching:
    return NearestStationMatching()


def otp_codes() -> SecretsOtpGenerator:
    return SecretsOtpGenerator(settings().jwt_secret)


def verification_codes(session: SessionDep) -> SecretsVerificationCodeGenerator:
    length = SqlSettingsProvider(session).get_int("booking.verification_code_length", 4)
    return SecretsVerificationCodeGenerator(length)


@lru_cache(maxsize=1)
def sms() -> ConsoleSmsSender | FallbackSmsSender:
    """The sender the deployment configured.

    Cached: the fallback chain holds an httpx client, and building one per
    request would open a new connection pool for every sign-in.

    `sms_provider` has existed as a setting since the beginning and nothing
    read it, so every deployment used the console sender whatever it said --
    including, in principle, a production one, which would have delivered
    nothing and logged a success. config.load now refuses that outright, and
    this is the other half: a real provider to refuse in favour of.
    """
    configured = settings()
    if configured.sms_provider != "twilio":
        return ConsoleSmsSender()

    senders = [
        TwilioSmsSender(
            account_sid=configured.twilio_account_sid,
            auth_token=configured.twilio_auth_token,
            sender=sender,
        )
        # The sender ID first: it is what Ghorband's own networks -- Etisalat
        # and MTN -- require. The number is the fallback, and the only route to
        # AWCC.
        for sender in (configured.twilio_sender_id, configured.twilio_sender_number)
        if sender
    ]
    if not senders:
        raise ConfigurationError(
            "VELRO_SMS_PROVIDER is 'twilio' but neither VELRO_TWILIO_SENDER_ID "
            "nor VELRO_TWILIO_SENDER_NUMBER is set: there is nothing to send from"
        )
    return FallbackSmsSender(senders)


def push() -> ConsolePushChannel:
    return ConsolePushChannel()


# -- authentication ------------------------------------------------------

class Actor:
    """Who is making this request. Constructed once, per request."""

    def __init__(self, user_id: str, roles: list[str]) -> None:
        self.user_id = user_id
        self.roles = roles

    @property
    def is_staff(self) -> bool:
        return bool(set(self.roles) & STAFF_ROLES)

    @property
    def role(self) -> ActorRole:
        if self.is_staff:
            return ActorRole.DISPATCHER if DISPATCHER in self.roles else ActorRole.ADMIN
        if DRIVER in self.roles:
            return ActorRole.DRIVER
        return ActorRole.PASSENGER

    def require(self, *roles: str) -> None:
        if not set(roles) & set(self.roles):
            raise PermissionError(
                error_codes.PERMISSION_DENIED,
                required=sorted(roles),
                actor_id=self.user_id,
            )


def current_actor(
    request: Request,
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> Actor:
    """Who is making this request, confirmed against the database.

    The claims inside a token are a cache, not the authority. A signed token
    stays valid until it expires, so trusting its ``roles`` means a revoked
    role, a suspended account or a deleted user keeps working for the lifetime
    of the access token -- fifteen minutes during which someone who has just
    been suspended can still approve drivers and change prices.

    So the user is re-read on every authenticated request and the roles come
    from the database. Two primary-key lookups against small, hot, indexed
    tables; the cost is not measurable next to what the request goes on to do,
    and it makes "suspend this account" mean now rather than eventually.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthenticationError(error_codes.TOKEN_INVALID)

    claims = tokens().read_access_token(authorization.split(" ", 1)[1].strip())
    user_id = claims.get("sub")
    if not user_id:
        raise AuthenticationError(error_codes.TOKEN_INVALID)

    users_repo = UserRepository(session)
    row = users_repo.find(user_id)
    if row is None:
        # A token signed for a user who no longer exists. Valid signature,
        # absent subject.
        raise AuthenticationError(error_codes.USER_NOT_FOUND, user_id=user_id)
    if row.status != UserStatus.ACTIVE.value:
        raise AuthenticationError(
            error_codes.USER_SUSPENDED, user_id=user_id, status=row.status
        )

    actor = Actor(user_id=row.id, roles=users_repo.roles_of(row.id))
    request.state.actor_id = actor.user_id
    return actor


ActorDep = Annotated[Actor, Depends(current_actor)]


def require_driver(actor: ActorDep) -> Actor:
    actor.require(DRIVER)
    return actor


def require_staff(actor: ActorDep) -> Actor:
    actor.require(*STAFF_ROLES)
    return actor


def require_admin(actor: ActorDep) -> Actor:
    actor.require(SUPER_ADMIN, ADMIN)
    return actor


def require_operations(actor: ActorDep) -> Actor:
    actor.require(SUPER_ADMIN, ADMIN, OPERATIONS_MANAGER, DISPATCHER)
    return actor


def require_finance(actor: ActorDep) -> Actor:
    actor.require(SUPER_ADMIN, ADMIN, FINANCE_MANAGER)
    return actor


#: Who may act on a support request as staff.
#:
#: Narrower than STAFF_ROLES on purpose. A finance manager and a dispatcher are
#: staff, and neither should be reading a report that may describe an assault
#: or writing notes on it.
SUPPORT_STAFF_ROLES = frozenset({SUPER_ADMIN, ADMIN, SUPPORT_AGENT})


def require_support(actor: ActorDep) -> Actor:
    actor.require(*SUPPORT_STAFF_ROLES)
    return actor


def is_support_staff(actor: Actor) -> bool:
    """The same rule as require_support, for the endpoints that must not 403.

    Deliberately reads actor.roles rather than actor.role: the latter collapses
    all six staff roles into DISPATCHER or ADMIN, so a check written against it
    hands a finance manager the same powers over a safety report as a support
    agent -- while the queue endpoint next to it refuses them. Two gates on one
    feature that disagree is worse than either gate alone.
    """
    return bool(set(actor.roles) & SUPPORT_STAFF_ROLES)


__all__ = [
    "PASSENGER",
    "Actor",
    "ActorDep",
    "DestinationRepository",
    "DistrictRepository",
    "RideRequestRepository",
    "RouteScheduleRepository",
    "RouteStopRepository",
    "RouteTemplateRepository",
    "SessionDep",
    "SettlementRepository",
    "StationRepository",
    "SupportTicketRepository",
    "TicketMessageRepository",
    "VillageRepository",
    "app_settings",
    "audit",
    "bookings",
    "cancellations",
    "clock",
    "commissions",
    "current_actor",
    "db_session",
    "driver_locations",
    "drivers",
    "fare_strategy",
    "fares",
    "geography",
    "idempotency",
    "is_support_staff",
    "matching",
    "new_id",
    "notifications",
    "numbers",
    "offers",
    "otp_codes",
    "otps",
    "payments",
    "push",
    "ratings",
    "refresh_tokens",
    "require_admin",
    "require_driver",
    "require_finance",
    "require_operations",
    "require_staff",
    "require_support",
    "routes",
    "seats",
    "settings",
    "sms",
    "tokens",
    "trips",
    "users",
    "vehicles",
    "verification_codes",
    "wallets",
]
