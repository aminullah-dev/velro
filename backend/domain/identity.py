"""Identity, roles and one-time passwords.

Phone plus OTP is the primary flow: most passengers in the target market do not
have email, and a password is one more thing to lose. The OTP itself is never
stored -- only a hash -- and never logged.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass, field
from datetime import datetime

from domain.enums import ActorRole, Locale, UserStatus
from shared import error_codes
from shared.errors import AuthenticationError, ConflictError, ValidationError, PermissionError as DomainPermissionError

# The eight roles of section 58. Roles are fixed; the permissions attached to
# them are rows, so an operator can retune a role without a deploy.
SUPER_ADMIN = "SUPER_ADMIN"
ADMIN = "ADMIN"
OPERATIONS_MANAGER = "OPERATIONS_MANAGER"
DISPATCHER = "DISPATCHER"
FINANCE_MANAGER = "FINANCE_MANAGER"
SUPPORT_AGENT = "SUPPORT_AGENT"
DRIVER = "DRIVER"
PASSENGER = "PASSENGER"

ALL_ROLES: tuple[str, ...] = (
    SUPER_ADMIN, ADMIN, OPERATIONS_MANAGER, DISPATCHER,
    FINANCE_MANAGER, SUPPORT_AGENT, DRIVER, PASSENGER,
)

STAFF_ROLES: frozenset[str] = frozenset(
    {SUPER_ADMIN, ADMIN, OPERATIONS_MANAGER, DISPATCHER, FINANCE_MANAGER, SUPPORT_AGENT}
)


@dataclass(frozen=True, slots=True)
class PhoneNumber:
    """E.164, stored normalised. Afghanistan is +93 and drops the trunk zero."""

    value: str

    def __post_init__(self) -> None:
        if not self.value.startswith("+") or not self.value[1:].isdigit():
            raise ValidationError(error_codes.PHONE_INVALID, phone=_mask(self.value))
        if not 8 <= len(self.value) - 1 <= 15:
            raise ValidationError(error_codes.PHONE_INVALID, phone=_mask(self.value))

    @classmethod
    def parse(cls, raw: str, *, default_country_code: str = "93") -> PhoneNumber:
        digits = "".join(ch for ch in raw.strip() if ch.isdigit() or ch == "+")
        if digits.startswith("+"):
            return cls(digits)
        if digits.startswith("00"):
            return cls("+" + digits[2:])
        if digits.startswith(default_country_code) and len(digits) > 9:
            return cls("+" + digits)
        return cls("+" + default_country_code + digits.lstrip("0"))

    @property
    def masked(self) -> str:
        return _mask(self.value)

    def __str__(self) -> str:
        return self.value


def _mask(value: str) -> str:
    """Phone numbers are personal data; logs and error contexts get this form."""
    return value[:4] + "*" * max(0, len(value) - 6) + value[-2:] if len(value) > 6 else "***"


@dataclass(slots=True)
class User:
    id: str
    phone: PhoneNumber
    full_name: str | None = None
    locale: Locale = Locale.DARI
    photo_key: str | None = None
    status: UserStatus = UserStatus.ACTIVE
    roles: set[str] = field(default_factory=set)
    last_seen_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, UserStatus):
            self.status = UserStatus(self.status)
        if not isinstance(self.locale, Locale):
            self.locale = Locale(self.locale)

    @property
    def is_active(self) -> bool:
        return self.status is UserStatus.ACTIVE

    def assert_active(self) -> None:
        if not self.is_active:
            raise AuthenticationError(
                error_codes.USER_SUSPENDED, user_id=self.id, status=str(self.status)
            )

    def suspend(self) -> None:
        """The operator's off switch for one account.

        Staff are refused here, not out of courtesy to staff: an administrator
        who can suspend another administrator -- or himself -- can lock the
        door of the whole office from inside. Staff misconduct is a role
        revocation, which a different administrator performs.

        Only an ACTIVE account can move to SUSPENDED. A DEACTIVATED account is
        already off in a different way, and layering the two states silently
        would leave nobody sure which switch turned it off.
        """
        if self.is_staff:
            raise DomainPermissionError(
                error_codes.PERMISSION_DENIED, user_id=self.id, reason="staff_account"
            )
        if self.status is not UserStatus.ACTIVE:
            raise ConflictError(
                error_codes.USER_ALREADY_SUSPENDED, user_id=self.id, status=str(self.status)
            )
        self.status = UserStatus.SUSPENDED

    def reinstate(self) -> None:
        """Strictly the reverse of suspend, and only that.

        Reinstating a DEACTIVATED account through this door would resurrect an
        account its owner closed, on an administrator's tap.
        """
        if self.status is not UserStatus.SUSPENDED:
            raise ConflictError(
                error_codes.USER_NOT_SUSPENDED, user_id=self.id, status=str(self.status)
            )
        self.status = UserStatus.ACTIVE

    def has_role(self, role: str) -> bool:
        return role in self.roles

    @property
    def is_staff(self) -> bool:
        return bool(self.roles & STAFF_ROLES)

    def primary_actor_role(self) -> ActorRole:
        if self.roles & STAFF_ROLES:
            return ActorRole.DISPATCHER if DISPATCHER in self.roles else ActorRole.ADMIN
        if DRIVER in self.roles:
            return ActorRole.DRIVER
        return ActorRole.PASSENGER


@dataclass(slots=True)
class OtpChallenge:
    """A single-use, expiring, rate-limited login code.

    ``code_hash`` is what is stored. The plaintext exists only in the SMS the
    passenger receives and in the request that verifies it.
    """

    id: str
    phone: PhoneNumber
    code_hash: str
    expires_at: datetime
    max_attempts: int
    attempts: int = 0
    consumed_at: datetime | None = None

    def verify(self, candidate_hash: str, *, at: datetime) -> None:
        if self.consumed_at is not None:
            raise ConflictError(error_codes.OTP_ALREADY_CONSUMED, phone=self.phone.masked)
        if at >= self.expires_at:
            raise AuthenticationError(error_codes.OTP_EXPIRED, phone=self.phone.masked)
        if self.attempts >= self.max_attempts:
            raise AuthenticationError(
                error_codes.OTP_ATTEMPTS_EXCEEDED, phone=self.phone.masked
            )

        self.attempts += 1
        if not hmac.compare_digest(candidate_hash, self.code_hash):
            remaining = max(0, self.max_attempts - self.attempts)
            raise AuthenticationError(
                error_codes.OTP_INVALID, phone=self.phone.masked, attempts_remaining=remaining
            )
        self.consumed_at = at

    @property
    def is_consumed(self) -> bool:
        return self.consumed_at is not None


@dataclass(slots=True)
class RefreshToken:
    """Server-side and revocable, so 'log out all devices' is a real operation."""

    id: str
    user_id: str
    token_hash: str
    device_id: str | None
    expires_at: datetime
    revoked_at: datetime | None = None
    replaced_by_id: str | None = None
    user_agent: str | None = None

    def assert_usable(self, *, at: datetime) -> None:
        if self.revoked_at is not None:
            raise AuthenticationError(error_codes.REFRESH_TOKEN_REVOKED, token_id=self.id)
        if at >= self.expires_at:
            raise AuthenticationError(error_codes.TOKEN_EXPIRED, token_id=self.id)

    def revoke(self, *, at: datetime, replaced_by_id: str | None = None) -> None:
        if self.revoked_at is None:
            self.revoked_at = at
        self.replaced_by_id = replaced_by_id
