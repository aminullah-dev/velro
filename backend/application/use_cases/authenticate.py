"""Phone + OTP authentication.

Most passengers in the target market have no email address, and a password is
one more thing to lose. The code is hashed with a phone-salted HMAC, single-use,
short-lived, and rate-limited per number -- an SMS gateway costs money per
message, so an unthrottled endpoint is both a security hole and a bill.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, NoReturn

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
from domain.identity import (
    PASSENGER,
    STAFF_ROLES,
    OtpChallenge,
    PhoneNumber,
    User,
)
from shared import error_codes
from shared.clock import Clock
from shared.errors import AuthenticationError, ConflictError, RateLimitError
from shared.ids import IdGenerator
from shared.logging import get_logger

log = get_logger(__name__)

#: The handsets. Anybody may ask for a code, because anybody may open an
#: account -- that is the product.
APP_AUDIENCE = "app"
#: The operator console. The people who belong here are already known, so a
#: number without a staff role is answered but never sent to.
STAFF_AUDIENCE = "staff"

#: The console's own channel. An inbox is free where a carrier charges
#: nearly half a dollar, and it is reachable from a laptop anywhere -- which
#: a SIM in a drawer in Parwan is not. Only staff, only with an address on
#: file; the handsets never see it.
EMAIL_CHANNEL = "email"


@dataclass(frozen=True, slots=True)
class RequestOtpCommand:
    phone: str
    locale: str = Locale.DARI.value
    request_ip: str | None = None
    #: Where the person asked for the code. "telegram" is a cent and needs
    #: the handset online; "sms" is forty-five cents and reaches a phone with
    #: no data at all. They know which they are; we do not.
    channel: str = "sms"
    #: Which front door this came from. "app" is the passenger and driver
    #: handsets: anybody may ask, because anybody may open an account. "staff"
    #: is the operator console, where the set of people who belong is already
    #: known -- so a number without a staff role gets no code and costs no
    #: message. See RequestOtp._is_staff.
    audience: str = "app"


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
        #: The mail channel for console codes. None means no server is set
        #: and a console code goes by SMS -- a configuration, not a failure.
        email: Any | None = None,
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
        self._email = email
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

    def _is_staff(self, phone: PhoneNumber) -> bool:
        return self._staff_account(phone) is not None

    def _staff_account(self, phone: PhoneNumber) -> Any | None:
        """The account behind this number, if it holds a role that opens the
        console; None for everybody else.

        Read from user_roles, not from a list in configuration. A list has to
        be edited on the server every time somebody is hired or let go, and
        the day it disagrees with the database is the day a person removed
        from the roles table still receives console codes. The roles table is
        already the thing every request is authorised against; asking it here
        means there is one answer to the question, not two.

        A suspended account is refused too. It would be turned away at the
        next request anyway, so sending it a code only spends a message to
        arrive at the same place.
        """
        user = self._users.find_by_phone(phone.value)
        if user is None or user.status != UserStatus.ACTIVE.value:
            return None
        if not STAFF_ROLES & set(self._users.roles_of(user.id)):
            return None
        return user

    def execute(self, cmd: RequestOtpCommand) -> RequestOtpResult:
        phone = PhoneNumber.parse(cmd.phone, default_country_code=_country(self._settings))
        now = self._clock.now()

        window = self._settings.get_int("otp.resend_window_seconds", 60)
        max_per_window = self._settings.get_int("otp.max_per_window", 3)
        # The count and the insert below are one step per number: without the
        # lock, requests that arrive together all count the same total and
        # all pass, and every one of them is an SMS somebody pays for.
        self._otps.lock_phone(phone.value)
        recent = self._otps.count_recent(phone.value, since=now - timedelta(seconds=window))
        if recent >= max_per_window:
            # The error carries the masked number only: an error context is
            # logged, and a full phone number in a log is personal data.
            raise RateLimitError(
                error_codes.OTP_RATE_LIMITED,
                phone=phone.masked,
                retry_after_seconds=window,
            )

        ttl = self._settings.get_int("otp.ttl_seconds", 300)

        staff = self._staff_account(phone) if cmd.audience == STAFF_AUDIENCE else None
        if cmd.audience == STAFF_AUDIENCE and staff is None:
            # Not an error, and deliberately indistinguishable from success.
            #
            # Answering "that number is not staff" would turn this endpoint
            # into a directory of who runs the service: anybody could walk a
            # list of numbers and learn which ones open the console. So the
            # console gets the same answer either way, no challenge is
            # created, and no message is paid for.
            #
            # The cost of that choice is that somebody who mistypes their own
            # number waits for a code that never arrives. For a door with a
            # handful of keyholders who know their own numbers, that is a
            # better trade than telling a stranger which keys exist.
            log.warning(
                "auth.otp.staff_only_refused",
                phone=phone.masked,
                detail="console code requested for a number with no staff role",
            )
            return RequestOtpResult(
                expires_in_seconds=ttl,
                resend_after_seconds=window,
                debug_code=None,
                channel="sms",
            )

        length = self._settings.get_int("otp.length", 5)
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
        if is_test_number and self._is_staff(phone):
            # A listed number is handed its code in the API response, to
            # whoever asked. For a passenger's test handset that is a free
            # sign-in during development. For an account that opens the
            # console it is the console, handed to the internet: the seed's
            # +93700000001 sat on this list on the production server with
            # SUPER_ADMIN, and two unauthenticated requests were a full
            # takeover. So a staff account is never a test number, whatever
            # the list says -- it takes the real path, at real cost, and the
            # log says why. debug_echo is untouched: that switch is refused
            # in production by config.load and is how the suites sign in.
            log.error(
                "auth.otp.staff_test_number_ignored",
                phone=phone.masked,
                detail="a staff account is on OTP_TEST_NUMBERS; sending for real instead",
            )
            is_test_number = False
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
            # The console's inbox first, when it asked for it and has one.
            # Then Telegram, if they asked for it and the deployment has it:
            # a cent instead of forty-five, and it reaches a phone that is
            # online -- which is why the person choosing is the right person
            # to decide: they know whether they use Telegram, and we do not.
            # Then the carrier, which reaches a phone with no data at all.
            if (
                cmd.channel == EMAIL_CHANNEL
                and staff is not None
                and staff.email
                and self._email is not None
                and self._email.send(
                    to=staff.email,
                    subject_key="auth.email.otp_subject",
                    message_key="auth.email.otp",
                    payload=payload,
                    locale=cmd.locale,
                )
            ):
                channel = EMAIL_CHANNEL
            elif (
                cmd.channel == "telegram"
                and self._telegram is not None
                and self._telegram.send(
                    phone=phone, message_key="auth.sms.otp",
                    payload=payload, locale=cmd.locale,
                )
            ):
                channel = "telegram"

            if channel == "sms":
                # Either they asked for SMS, or the pipe they asked for would
                # not carry it -- no address on file, no mail server, not a
                # Telegram user, no data, an empty balance. Falling through
                # rather than failing is the whole point: nobody is locked
                # out of the product because the cheap pipe was shut, and the
                # answer says which pipe actually carried it.
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
        #: Spends one attempt in a transaction of its own and returns its
        #: number, or None when none is left. Its own transaction because a
        #: wrong code answers 401 and the request's transaction is rolled
        #: back with it -- which used to take the counter along, leaving a
        #: five-digit code guessable without limit. Without one (a caller
        #: that does not roll back on refusal) the request's own session
        #: spends it.
        reserve_attempt: Callable[[str], int | None] | None = None,
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
        self._reserve_attempt = reserve_attempt or otps.reserve_attempt

    def execute(self, cmd: VerifyOtpCommand) -> Session:
        phone = PhoneNumber.parse(cmd.phone, default_country_code=_country(self._settings))
        now = self._clock.now()

        row = self._otps.find_active(phone.value, at=now)
        if row is None:
            raise AuthenticationError(error_codes.OTP_EXPIRED, phone=phone.masked)

        # The attempt is spent before the code is compared, in one atomic
        # statement that also enforces the limit. Reading the counter and
        # writing it back let guesses that arrived together all read the
        # same count: twelve at once were twelve evaluated guesses against a
        # limit of five. Now the database hands out attempt numbers, and
        # there is no sixth.
        reserved = self._reserve_attempt(row.id)
        if reserved is None:
            raise AuthenticationError(
                error_codes.OTP_ATTEMPTS_EXCEEDED, phone=phone.masked
            )

        challenge = OtpChallenge(
            id=row.id,
            phone=phone,
            code_hash=row.code_hash,
            expires_at=row.expires_at,
            max_attempts=row.max_attempts,
            # The domain counts the attempt it is about to make; this one is
            # already paid for, so it starts one short of the number it got.
            attempts=reserved - 1,
            consumed_at=row.consumed_at,
        )
        challenge.verify(self._codes.hash(cmd.code, phone), at=now)

        # One code, one session. Two requests that both matched it race to
        # this conditional update; the loser finds it already consumed.
        if not self._otps.consume(row.id, at=now):
            raise ConflictError(error_codes.OTP_ALREADY_CONSUMED, phone=phone.masked)

        user_row = self._users.find_by_phone(phone.value)
        is_new = user_row is None
        if user_row is None:
            # A second first sign-in for the same new number may be creating
            # the account in this same instant; whichever inserts second is
            # handed the account the other made, roles and all, instead of a
            # 500. Still a new user from this handset's point of view: the
            # account is seconds old and nobody has named it yet.
            user_row, created = self._users.create_or_find(
                id=self._new_id(), phone=phone.value, locale=cmd.locale, full_name=None
            )
            if created:
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
        #: Ends every session of a user in a transaction of its own. A replay
        #: answers 401, and the request's transaction is rolled back with it
        #: -- which used to take the revocation along, leaving the thief's
        #: copy and every other session refreshing as if nothing happened.
        revoke_on_reuse: Callable[[str, datetime], None] | None = None,
    ) -> None:
        self._users = users
        self._refresh = refresh_tokens
        self._tokens = tokens
        self._clock = clock
        self._new_id = new_id
        self._access_ttl = access_ttl_seconds
        self._refresh_ttl = refresh_ttl_seconds
        self._revoke_on_reuse = revoke_on_reuse

    def execute(self, cmd: RefreshSessionCommand) -> Session:
        now = self._clock.now()
        presented_hash = self._tokens.hash_refresh_token(cmd.refresh_token)

        row = self._refresh.find_by_hash(presented_hash)
        if row is None:
            raise AuthenticationError(error_codes.TOKEN_INVALID)

        # The account first, whatever the state of the token. current_actor
        # refuses a suspended account on every request, and this did not: a
        # suspended phone went on minting access tokens every fifteen minutes
        # and got its session back, without signing in, on the day it was
        # reinstated. suspend_user now revokes the tokens as well; this
        # covers every account suspended before it did, and anything that
        # changes a status by another road. The same error current_actor
        # gives, so the app says "suspended" rather than signing out silently.
        user_row = self._users.find(row.user_id)
        if user_row is None:
            raise AuthenticationError(error_codes.USER_NOT_FOUND, user_id=row.user_id)
        if user_row.status != UserStatus.ACTIVE.value:
            raise AuthenticationError(
                error_codes.USER_SUSPENDED, user_id=user_row.id, status=user_row.status
            )

        if row.revoked_at is not None:
            # A token that was already rotated is being presented again. Assume
            # the worst and end every session for this user.
            self._end_every_session(row.user_id, now)
        if now >= row.expires_at:
            raise AuthenticationError(error_codes.TOKEN_EXPIRED)

        roles = self._users.roles_of(user_row.id)

        # Retired conditionally, before the successor exists. The read above
        # took no lock, so a second request presenting the same token in the
        # same instant also got this far; whichever retires it second finds it
        # already retired and is a replay like any other. Unconditional, both
        # succeeded and one token became two live chains.
        replacement_id = self._new_id()
        if not self._refresh.rotate(row.id, at=now, replaced_by_id=replacement_id):
            self._end_every_session(row.user_id, now)

        plaintext, token_hash = self._tokens.new_refresh_token()
        self._refresh.create(
            id=replacement_id,
            user_id=user_row.id,
            token_hash=token_hash,
            device_id=cmd.device_id or row.device_id,
            user_agent=row.user_agent,
            expires_at=now + timedelta(seconds=self._refresh_ttl),
        )

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

    def _end_every_session(self, user_id: str, now: datetime) -> NoReturn:
        """A token presented after it was retired: theft. End everything.

        Not in this request's transaction: the refusal below is a 401, the
        middleware commits only responses under 400, and the revocation used
        to roll back with the answer that reported it. The revoker commits on
        its own, before the 401 leaves. Without one (a caller that does not
        roll back on refusal) the request's own transaction is the right place.
        """
        if self._revoke_on_reuse is not None:
            self._revoke_on_reuse(user_id, now)
        else:
            self._refresh.revoke_all_for_user(user_id, at=now)
        raise AuthenticationError(error_codes.REFRESH_TOKEN_REVOKED, user_id=user_id)


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
