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
    IdempotencyRepository,
    ImportJobRepository,
    NotificationRepository,
    RatingRepository,
    SupportTicketRepository,
)
from infrastructure.db.repositories.routing import (
    FareRepository,
    RouteRepository,
    RouteScheduleRepository,
    RouteStopRepository,
    RouteTemplateRepository,
)
from infrastructure.db.repositories.seats import TripSeatRepository
from infrastructure.db.repositories.supply import (
    DriverDocumentRepository,
    DriverLocationRepository,
    DriverRepository,
    VehicleRepository,
)
from infrastructure.db.repositories.trips import (
    BookingRepository,
    DispatchOfferRepository,
    RideRequestRepository,
    TripRepository,
)
from infrastructure.db.session import build_engine, build_session_factory
from infrastructure.services.audit import SqlAuditLog
from infrastructure.services.codes import SecretsOtpGenerator, SecretsVerificationCodeGenerator
from infrastructure.services.messaging import ConsolePushChannel, ConsoleSmsSender
from infrastructure.services.numbers import SqlNumberAllocator
from infrastructure.services.settings import SqlSettingsProvider
from infrastructure.services.storage import LocalFileStorage
from infrastructure.services.tokens import JwtTokenService
from shared import config, error_codes
from shared.clock import SystemClock
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


def driver_locations(session: SessionDep) -> DriverLocationRepository:
    return DriverLocationRepository(session)


def driver_documents(session: SessionDep) -> DriverDocumentRepository:
    return DriverDocumentRepository(session)


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


def ratings(session: SessionDep) -> RatingRepository:
    return RatingRepository(session)


def cancellations(session: SessionDep) -> CancellationRepository:
    return CancellationRepository(session)


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


def sms() -> ConsoleSmsSender:
    return ConsoleSmsSender()


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


def require_support(actor: ActorDep) -> Actor:
    actor.require(SUPER_ADMIN, ADMIN, SUPPORT_AGENT)
    return actor


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
