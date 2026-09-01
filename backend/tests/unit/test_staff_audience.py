"""Who is allowed to make the operator console send a code.

The console used to ask the same public endpoint the handsets ask, with no
way of saying it was the console asking. So typing any number at all into the
admin sign-in screen sent a real SMS to a real stranger, at real cost, from a
budget of roughly a hundred messages a month. A script pointed at that form
could empty the balance and put a code on a lot of phones that never asked
for one.

The rule these tests hold in place: a code for the console goes only to a
number that already holds a staff role, and every other number gets the
identical answer with nothing sent. Identical is the load-bearing word -- a
distinguishable refusal would let anyone walk a list of numbers and learn
which ones run the service.

Staff-ness is read from user_roles, never from a list in configuration, so
there is one answer to the question rather than two that can drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar

import pytest

from application.use_cases.authenticate import RequestOtp, RequestOtpCommand

STAFF = "+93700000801"
PASSENGER = "+93700000802"
STRANGER = "+93700000803"
SUSPENDED_STAFF = "+93700000804"


@dataclass
class FakeOtps:
    rows: list[Any] = field(default_factory=list)

    def count_recent(self, phone: str, *, since: datetime) -> int:
        return 0

    def create(self, **fields: Any) -> Any:
        self.rows.append(fields)
        return fields

    def save(self, row: Any) -> Any:
        return row


@dataclass
class Row:
    id: str
    status: str = "ACTIVE"


class FakeUsers:
    """Four numbers: one admin, one passenger, one nobody, one suspended admin."""

    _BY_PHONE: ClassVar[dict[str, Row]] = {
        STAFF: Row("u-staff"),
        PASSENGER: Row("u-passenger"),
        SUSPENDED_STAFF: Row("u-suspended", status="SUSPENDED"),
    }
    _ROLES: ClassVar[dict[str, list[str]]] = {
        "u-staff": ["SUPER_ADMIN", "PASSENGER"],
        "u-passenger": ["PASSENGER", "DRIVER"],
        "u-suspended": ["ADMIN"],
    }

    def find_by_phone(self, phone: str) -> Row | None:
        return self._BY_PHONE.get(phone)

    def roles_of(self, user_id: str) -> list[str]:
        return self._ROLES[user_id]


class FakeCodes:
    def generate(self, length: int) -> str:
        return "13579"[:length]

    def hash(self, code: str, phone: Any) -> str:
        return f"hashed:{code}"


@dataclass
class FakeSms:
    sent: list[dict[str, Any]] = field(default_factory=list)

    def send(self, **fields: Any) -> bool:
        self.sent.append(fields)
        return True


class FakeSettings:
    def get_int(self, key: str, default: int) -> int:
        return default

    def get_str(self, key: str, default: str = "") -> str:
        return "93" if "country" in key else default


class FrozenClock:
    def now(self) -> datetime:
        return datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def request(phone: str, *, audience: str = "app", debug_echo: bool = False):
    sms = FakeSms()
    otps = FakeOtps()
    use_case = RequestOtp(
        users=FakeUsers(),
        otps=otps,
        codes=FakeCodes(),
        sms=sms,
        settings=FakeSettings(),
        clock=FrozenClock(),
        new_id=lambda: "01900000-0000-7000-8000-00000000000b",
        debug_echo=debug_echo,
    )
    result = use_case.execute(
        RequestOtpCommand(phone=phone, locale="fa-AF", audience=audience)
    )
    return result, sms, otps


class TestTheConsole:
    def test_a_staff_number_gets_its_code(self) -> None:
        _, sms, otps = request(STAFF, audience="staff")
        assert len(sms.sent) == 1
        assert len(otps.rows) == 1

    @pytest.mark.parametrize("phone", [PASSENGER, STRANGER, SUSPENDED_STAFF])
    def test_everyone_else_costs_nothing(self, phone: str) -> None:
        """The bill is the point. No message means no charge."""
        _, sms, _ = request(phone, audience="staff")
        assert sms.sent == []

    @pytest.mark.parametrize("phone", [PASSENGER, STRANGER, SUSPENDED_STAFF])
    def test_and_leaves_no_challenge_to_guess(self, phone: str) -> None:
        """No row means there is nothing for a guessing loop to hit."""
        _, _, otps = request(phone, audience="staff")
        assert otps.rows == []

    @pytest.mark.parametrize("phone", [PASSENGER, STRANGER, SUSPENDED_STAFF])
    def test_the_refusal_is_indistinguishable_from_success(self, phone: str) -> None:
        """The half that stops this being a directory of who runs VELRO.

        If a refused number answered differently -- another error code, another
        expiry, a different resend window -- anybody could walk a list of
        numbers and read off which ones open the console. Then they would know
        exactly whose handset to go after.
        """
        allowed, _, _ = request(STAFF, audience="staff")
        refused, _, _ = request(phone, audience="staff")
        assert refused == allowed

    def test_a_suspended_admin_is_turned_away_here_too(self) -> None:
        """He would be refused at his next request anyway; sending the code
        first only spends a message to arrive at the same place."""
        _, sms, _ = request(SUSPENDED_STAFF, audience="staff")
        assert sms.sent == []

    def test_a_refused_number_never_gets_a_code_in_the_response(self) -> None:
        """Development echoes codes. It must not echo one it refused to make,
        or the console would hand a stranger a working code on localhost."""
        result, _, _ = request(STRANGER, audience="staff", debug_echo=True)
        assert result.debug_code is None


class TestTheHandsets:
    """The other half: the product still belongs to anybody with a phone."""

    @pytest.mark.parametrize("phone", [PASSENGER, STRANGER, SUSPENDED_STAFF, STAFF])
    def test_anybody_may_ask_the_app_for_a_code(self, phone: str) -> None:
        _, sms, _ = request(phone, audience="app")
        assert len(sms.sent) == 1

    def test_app_is_the_default(self) -> None:
        """Every client that predates this change sends no audience at all.

        If the default were "staff", shipping this would lock every passenger
        in Ghorband out of an app already on their phone.
        """
        assert RequestOtpCommand(phone=STRANGER).audience == "app"
