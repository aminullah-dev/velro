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
from infrastructure.db.repositories.erasure import AccountEraser
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
from infrastructure.services.storage import DiscardOnRollbackStorage, LocalFileStorage
from infrastructure.services.tokens import JwtTokenService
from shared import config, error_codes
from shared.clock import SystemClock
from shared.config import ConfigurationError
from shared.errors import AuthenticationError, PermissionError
from shared.ids import new_id
from shared.logging import get_logger
from ui.api.session_scope import current_session, on_rollback

log = get_logger(__name__)


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


@lru_cache(maxsize=1)
def telegram_sender():
    """The Telegram channel, or None when nobody has opened an account.

    Cached beside sms() and for the same reason: it holds an HTTP client, and
    building one per sign-in would open a connection pool per request.
    """
    from infrastructure.services.sms import TelegramGatewaySender

    token = settings().telegram_gateway_token
    return TelegramGatewaySender(token=token) if token else None


@lru_cache(maxsize=1)
def email_sender():
    """The mail channel for console codes, or None when no server is set.

    Cached for the same reason as sms(): the config is read once, and the
    object is stateless between messages.
    """
    from infrastructure.services.email import SmtpEmailSender

    cfg = settings()
    if not cfg.smtp_host:
        return None
    return SmtpEmailSender(
        host=cfg.smtp_host,
        port=cfg.smtp_port,
        username=cfg.smtp_username,
        password=cfg.smtp_password,
        sender=cfg.smtp_from or cfg.smtp_username,
    )


def otp_attempt_reserver():
    """Spend an OTP attempt where a refusal cannot undo it.

    The request transaction commits only on a successful response, which is
    right for everything except this: a wrong code returns 401, the rollback
    takes the attempt counter with it, and a five-digit code becomes
    guessable without limit. Verified before fixing -- three wrong codes in a
    row each answered "4 attempts remaining" and left attempts = 0 in the
    database.

    So the attempt is spent in its own short transaction, committed before
    the code is even compared. And it is spent with one conditional
    ``attempts = attempts + 1`` (OtpRepository.reserve_attempt), not by
    writing back a count read earlier: that was the second hole, where
    guesses arriving together all read the same count and twelve at once
    were twelve evaluated guesses against a limit of five.

    No row lock is taken in the request's own session, and that is
    deliberate: this transaction would then wait on its own request.

    A failure to spend the attempt is not swallowed. Comparing a code whose
    attempt could not be counted is exactly the unlimited guessing this
    exists to prevent, so the request fails instead -- and a database that
    cannot take one UPDATE was not going to sign anybody in anyway.
    """

    def reserve(challenge_id: str) -> int | None:
        with _session_factory()() as own:
            reserved = OtpRepository(own).reserve_attempt(challenge_id)
            own.commit()
        return reserved

    return reserve


def refresh_reuse_revoker():
    """End every session of a user where a refusal cannot undo it.

    The same trap as otp_attempt_reserver, on the other half of sign-in. A
    refresh token presented a second time has been copied, so RefreshSession
    revokes every session the user has -- and then answers 401, which rolls
    the request's transaction back and the revocation with it. Verified
    before fixing: after a replay was refused, the user's other session and
    the rotated successor both went on refreshing.

    So the revocation travels in its own short transaction, committed before
    the 401 leaves. Failing to write it must not turn the refusal into a 500:
    the replay is refused either way, and the operator gets a log line loud
    enough to act on by hand (POST /auth/logout-all as that user, or the
    refresh_tokens table).
    """
    from datetime import datetime

    def revoke(user_id: str, at: datetime) -> None:
        try:
            with _session_factory()() as own:
                revoked = RefreshTokenRepository(own).revoke_all_for_user(user_id, at=at)
                own.commit()
            log.warning("auth.refresh_reuse_revoked", user_id=user_id, revoked=revoked)
        except Exception as exc:
            log.error(
                "auth.refresh_reuse_not_revoked",
                user_id=user_id,
                error=type(exc).__name__,
            )

    return revoke


def boarding_attempt_reserver():
    """Spend a boarding-code attempt where a refusal cannot undo it.

    otp_attempt_reserver's twin, for the code a driver types to board a
    passenger: every wrong code is a 409, the request's transaction rolls
    back with it, and a counter kept there would never move. So the attempt
    is spent -- and the lockout set, when it is the last one -- in a short
    transaction of its own, committed before the code is compared, with one
    conditional UPDATE (TripRepository.reserve_boarding_attempt) so that
    simultaneous attempts cannot read the same count.

    Not swallowed on failure, for the same reason as the OTP one: a code
    whose attempt could not be counted must not be compared.
    """
    from datetime import datetime

    def reserve(
        trip_id: str, *, at: datetime, max_attempts: int, lockout_seconds: int
    ) -> tuple[int | None, datetime | None]:
        with _session_factory()() as own:
            result = TripRepository(own).reserve_boarding_attempt(
                trip_id, at=at, max_attempts=max_attempts, lockout_seconds=lockout_seconds
            )
            own.commit()
        return result

    return reserve


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


def account_eraser(session: SessionDep) -> AccountEraser:
    return AccountEraser(session)


@lru_cache(maxsize=1)
def file_storage() -> LocalFileStorage:
    """Files live outside anything the web server serves.

    There is no URL that reaches them; the only way out is an endpoint that
    checks who is asking.
    """
    return LocalFileStorage(settings().storage_root)


def document_storage(session: SessionDep) -> DiscardOnRollbackStorage:
    """file_storage for a request that writes: a file put here is deleted
    again if the request's transaction rolls back. See on_rollback."""
    return DiscardOnRollbackStorage(
        file_storage(), lambda undo: on_rollback(session, undo)
    )


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
    length = SqlSettingsProvider(session).get_int("booking.verification_code_length", 6)
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
            api_key_sid=configured.twilio_api_key_sid or None,
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
    "email_sender",
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
