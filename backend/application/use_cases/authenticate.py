"""Phone + OTP authentication.

Most passengers in the target market have no email address, and a password is
one more thing to lose. The code is hashed with a phone-salted HMAC, single-use,
short-lived, and rate-limited per number -- an SMS gateway costs money per
message, so an unthrottled endpoint is both a security hole and a bill.
"""

from __future__ import annotations

from collections.abc import Callable

from dataclasses import dataclass
from datetime import timedelta

from application.ports.repositories import (
    OtpRepository,
    RefreshTokenRepository,
    UserRepository,
)
from application.ports.services import (
    AuditLog,
    OtpCodeGenerator,
    SettingsProvider,
    SmsSender,
    TokenService,
)
from domain.enums import Locale, UserStatus
from domain.identity import PASSENGER, OtpChallenge, PhoneNumber, User
from shared import error_codes
from shared.clock import Clock
from shared.errors import AuthenticationError, RateLimitError
from shared.ids import IdGenerator
from shared.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RequestOtpCommand:
    phone: str
    locale: str = Locale.DARI.value
    request_ip: str | None = None
    #: Where the person asked for the code. "telegram" is a cent and needs
    #: the handset online; "sms" is forty-five cents and reaches a phone with
    #: no data at all. They know which they are; we do not.
    channel: str = "sms"


@dataclass(frozen=True, slots=True)
class RequestOtpResult:
    expires_in_seconds: int
    resend_after_seconds: int
    # Populated only when the deployment has otp_debug_echo on, which is never
    # true in production. It exists so a developer without an SMS gateway can
    # still log in.
    debug_code: str | None = None
    #: Which channel actually carried it, which is not always the one asked
    #: for: a Telegram code that cannot be delivered falls through to SMS,
    #: and the screen must say where to look rather than leave somebody
    #: staring at the wrong app.
    channel: str = "sms"


class RequestOtp:
    def __init__(
        self,
        *,
        users: UserRepository,
        otps: OtpRepository,
        codes: OtpCodeGenerator,
        sms: SmsSender,
        settings: SettingsProvider,
        clock: Clock,
        new_id: IdGenerator,
        debug_echo: bool = False,
        test_numbers: frozenset[str] = frozenset(),
        #: The Telegram channel, when the deployment has an account for it.
        #: None means the choice does not exist and every code is an SMS --
        #: which is a configuration, not a failure.
        telegram: Any | None = None,
    ) -> None:
        self._users = users
        self._otps = otps
        self._codes = codes
        self._sms = sms
        self._settings = settings
        self._clock = clock
        self._new_id = new_id
        self._debug_echo = debug_echo
        self._telegram = telegram
        # Numbers that skip the carrier and get their code in the response.
        #
        # Not the same thing as debug_echo, and deliberately so. debug_echo is
        # a switch for the whole deployment: with it on, anybody who knows any
        # phone number can ask this public API for that person's sign-in code.
        # config.load refuses to start production with it, and that stays.
        #
        # This is per-number and explicit. A number nobody listed always takes
        # the real path and always costs a real message, so listing the owner's
        # own handsets makes development free without making anyone else's
        # account reachable. Empty by default: absent configuration means
        # nobody, never everybody.
        self._test_numbers = test_numbers

    def execute(self, cmd: RequestOtpCommand) -> RequestOtpResult:
        phone = PhoneNumber.parse(cmd.phone, default_country_code=_country(self._settings))
        now = self._clock.now()

        window = self._settings.get_int("otp.resend_window_seconds", 60)
        max_per_window = self._settings.get_int("otp.max_per_window", 3)
        recent = self._otps.count_recent(phone.value, since=now - timedelta(seconds=window))
        if recent >= max_per_window:
            # The error carries the masked number only: an error context is
            # logged, and a full phone number in a log is personal data.
            raise RateLimitError(
                error_codes.OTP_RATE_LIMITED,
                phone=phone.masked,
                retry_after_seconds=window,
            )

        length = self._settings.get_int("otp.length", 5)
        ttl = self._settings.get_int("otp.ttl_seconds", 300)
        code = self._codes.generate(length)

        self._otps.create(
            id=self._new_id(),
            phone=phone.value,
            code_hash=self._codes.hash(code, phone),
            expires_at=now + timedelta(seconds=ttl),
            max_attempts=self._settings.get_int("otp.max_attempts", 5),
            request_ip=cmd.request_ip,
        )
        is_test_number = phone.value in self._test_numbers
        if is_test_number:
            # Logged at warning, every time, because a test number that
            # outlives the testing is a permanently unlocked account and the
            # only thing standing between it and being forgotten is this line
            # being loud in a production log.
            log.warning(
                "auth.otp.test_number",
                phone=phone.masked,
                detail="no SMS sent; the code is returned in the response",
            )
        channel = "sms"
        if not is_test_number:
            payload = {"code": code, "ttl_minutes": ttl // 60}
            # Telegram only if they asked for it and the deployment has it.
            # A cent instead of forty-five, and it reaches a phone that is
            # online -- which is why the person choosing is the right person
            # to decide: they know whether they use Telegram, and we do not.
            if cmd.channel == "telegram" and self._telegram is not None:
                if self._telegram.send(
                    phone=phone, message_key="auth.sms.otp",
                    payload=payload, locale=cmd.locale,
                ):
                    channel = "telegram"

            if channel != "telegram":
                # Either they asked for SMS, or Telegram would not carry it --
                # not a Telegram user, no data, an empty balance. Falling
                # through rather than failing is the whole point: nobody is
                # locked out of the product because the cheap pipe was shut.
                self._sms.send(
                    phone=phone,
                    message_key="auth.sms.otp",
                    payload=payload,
                    # The language they picked on the sign-in screen, before
                    # they have an account for it to be stored on.
                    locale=cmd.locale,
                )

        return RequestOtpResult(
            expires_in_seconds=ttl,
            resend_after_seconds=window,
            debug_code=code if (self._debug_echo or is_test_number) else None,
            channel=channel,
        )


@dataclass(frozen=True, slots=True)
class VerifyOtpCommand:
    phone: str
    code: str
    device_id: str | None = None
    user_agent: str | None = None
    locale: str = Locale.DARI.value


@dataclass(frozen=True, slots=True)
class Session:
    user_id: str
    access_token: str
    refresh_token: str
    roles: list[str]
    is_new_user: bool
    expires_in_seconds: int


class VerifyOtp:
    def __init__(
        self,
        *,
        users: UserRepository,
        otps: OtpRepository,
        refresh_tokens: RefreshTokenRepository,
        codes: OtpCodeGenerator,
        tokens: TokenService,
        settings: SettingsProvider,
        audit: AuditLog,
        clock: Clock,
        new_id: IdGenerator,
        access_ttl_seconds: int,
        refresh_ttl_seconds: int,
        #: Writes the attempt counter in a transaction of its own. A wrong
        #: code answers 401, and the request's transaction is rolled back
        #: with it -- which used to take the counter along, leaving a
        #: five-digit code guessable without limit.
        record_attempt: Callable[[str, int, datetime | None], None] | None = None,
    ) -> None:
        self._users = users
        self._otps = otps
        self._refresh = refresh_tokens
        self._codes = codes
        self._tokens = tokens
        self._settings = settings
        self._audit = audit
        self._clock = clock
        self._new_id = new_id
        self._access_ttl = access_ttl_seconds
        self._refresh_ttl = refresh_ttl_seconds
        self._record_attempt = record_attempt


    def execute(self, cmd: VerifyOtpCommand) -> Session:
        phone = PhoneNumber.parse(cmd.phone, default_country_code=_country(self._settings))
        now = self._clock.now()

        row = self._otps.find_active(phone.value, at=now)
        if row is None:
            raise AuthenticationError(error_codes.OTP_EXPIRED, phone=phone.masked)

        challenge = OtpChallenge(
            id=row.id,
            phone=phone,
            code_hash=row.code_hash,
            expires_at=row.expires_at,
            max_attempts=row.max_attempts,
            attempts=row.attempts,
            consumed_at=row.consumed_at,
        )
        try:
            challenge.verify(self._codes.hash(cmd.code, phone), at=now)
        finally:
            # The attempt counter must survive a refusal, and the request's
            # own transaction does not: the middleware commits only on a
            # response under 400, so every wrong code used to roll its own
            # counter back. Written twice on purpose -- into this
            # transaction, so a successful sign-in stays consistent with
            # everything else it does, and through the recorder, whose
            # transaction is already committed by the time the 401 leaves.
            row.attempts = challenge.attempts
            row.consumed_at = challenge.consumed_at
            self._otps.save(row)
            if self._record_attempt is not None:
                self._record_attempt(row.id, challenge.attempts, challenge.consumed_at)

        user_row = self._users.find_by_phone(phone.value)
        is_new = user_row is None
        if user_row is None:
            user_row = self._users.create(
                id=self._new_id(), phone=phone.value, locale=cmd.locale, full_name=None
            )
            self._users.grant_role(user_row.id, PASSENGER)

        user = User(
            id=user_row.id,
            phone=phone,
            full_name=user_row.full_name,
            locale=Locale(user_row.locale),
            status=UserStatus(user_row.status),
        )
        user.assert_active()

        roles = self._users.roles_of(user_row.id) or [PASSENGER]
        access = self._tokens.issue_access_token(
            user_id=user_row.id,
            roles=roles,
            expires_at=now + timedelta(seconds=self._access_ttl),
        )
        plaintext, token_hash = self._tokens.new_refresh_token()
        self._refresh.create(
            id=self._new_id(),
            user_id=user_row.id,
            token_hash=token_hash,
            device_id=cmd.device_id,
            user_agent=cmd.user_agent,
            expires_at=now + timedelta(seconds=self._refresh_ttl),
        )

        user_row.last_seen_at = now
        self._users.save(user_row)

        user.roles = set(roles)
        self._audit.write(
            "auth.signed_in",
            actor_id=user_row.id,
            # Derived from the roles actually granted. Hard-coding PASSENGER
            # here recorded every administrator's sign-in as a passenger's,
            # which is exactly the sort of quiet inaccuracy an audit trail
            # cannot afford -- it is trusted precisely because nobody re-checks
            # it.
            actor_role=user.primary_actor_role(),
            entity_type="user",
            entity_id=user_row.id,
            after={
                "is_new_user": is_new,
                # Omitted when absent rather than written as a null: an audit
                # diff should not carry fields that were never supplied.
                **({"device_id": cmd.device_id} if cmd.device_id else {}),
            },
        )

        return Session(
            user_id=user_row.id,
            access_token=access,
            refresh_token=plaintext,
            roles=roles,
            is_new_user=is_new,
            expires_in_seconds=self._access_ttl,
        )


@dataclass(frozen=True, slots=True)
class RefreshSessionCommand:
    refresh_token: str
    device_id: str | None = None


class RefreshSession:
    """Rotating refresh tokens: using one immediately replaces it.

    A replayed token is therefore detectable and is treated as theft -- every
    session for that user is revoked rather than the replay merely failing.
    """

    def __init__(
        self,
        *,
        users: UserRepository,
        refresh_tokens: RefreshTokenRepository,
        tokens: TokenService,
        clock: Clock,
        new_id: IdGenerator,
        access_ttl_seconds: int,
        refresh_ttl_seconds: int,
    ) -> None:
        self._users = users
        self._refresh = refresh_tokens
        self._tokens = tokens
        self._clock = clock
        self._new_id = new_id
        self._access_ttl = access_ttl_seconds
        self._refresh_ttl = refresh_ttl_seconds

    def execute(self, cmd: RefreshSessionCommand) -> Session:
        now = self._clock.now()
        presented_hash = self._tokens.hash_refresh_token(cmd.refresh_token)

        row = self._refresh.find_by_hash(presented_hash)
        if row is None:
            raise AuthenticationError(error_codes.TOKEN_INVALID)

        if row.revoked_at is not None:
            # A token that was already rotated is being presented again. Assume
            # the worst and end every session for this user.
            self._refresh.revoke_all_for_user(row.user_id, at=now)
            raise AuthenticationError(error_codes.REFRESH_TOKEN_REVOKED, user_id=row.user_id)
        if now >= row.expires_at:
            raise AuthenticationError(error_codes.TOKEN_EXPIRED)

        user_row = self._users.get(row.user_id)
        roles = self._users.roles_of(user_row.id)

        plaintext, token_hash = self._tokens.new_refresh_token()
        replacement_id = self._new_id()
        self._refresh.create(
            id=replacement_id,
            user_id=user_row.id,
            token_hash=token_hash,
            device_id=cmd.device_id or row.device_id,
            user_agent=row.user_agent,
            expires_at=now + timedelta(seconds=self._refresh_ttl),
        )
        row.revoked_at = now
        row.replaced_by_id = replacement_id
        self._refresh.save(row)

        access = self._tokens.issue_access_token(
            user_id=user_row.id,
            roles=roles,
            expires_at=now + timedelta(seconds=self._access_ttl),
        )
        return Session(
            user_id=user_row.id,
            access_token=access,
            refresh_token=plaintext,
            roles=roles,
            is_new_user=False,
            expires_in_seconds=self._access_ttl,
        )


def _country(settings) -> str:
    """Which country a number typed without a prefix belongs to.

    A row rather than a constant, for the same reason every other operational
    number is: Ghorband is +93, and a hardcoded 93 is exactly the kind of
    city-specific constant the product is supposed not to contain. It is also
    what lets somebody test against a real handset in another country without
    editing code -- otherwise "3438677631" silently becomes +933438677631, the
    code goes to an account nobody owns, and the failure looks like a broken
    OTP rather than a wrong country.

    Digits only. A malformed value would build an unparseable number for every
    user at once, so it falls back rather than propagating.
    """
    value = settings.get_str("auth.default_country_code", "93").strip().lstrip("+")
    return value if value.isdigit() and 1 <= len(value) <= 4 else "93"
