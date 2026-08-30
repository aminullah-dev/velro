"""Numbers that skip the carrier during development.

The owner is in Canada, the handsets are in Afghanistan, and every real code
costs about $0.45 against a ~$50/month budget. So development needs a way to
sign in without sending anything -- and it must not be the way that opens
every account at once.

The distinction these tests hold in place:

    otp_debug_echo     one switch, every number, refused in production
    otp_test_numbers   a named list, nobody else affected

If the second ever starts behaving like the first, a stranger who finds
api.velro.linumic.com can sign in as any passenger in Ghorband by asking for
their code. No database here: this is a decision about who gets an SMS, and
it should be provable without one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from application.use_cases.authenticate import RequestOtp, RequestOtpCommand

LISTED = "+93700000901"
UNLISTED = "+93700000902"


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


class FakeUsers:
    def find_by_phone(self, phone: str) -> None:
        return None


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
        return datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


def request(phone: str, *, listed: tuple[str, ...] = (), debug_echo: bool = False):
    sms = FakeSms()
    use_case = RequestOtp(
        users=FakeUsers(),
        otps=FakeOtps(),
        codes=FakeCodes(),
        sms=sms,
        settings=FakeSettings(),
        clock=FrozenClock(),
        new_id=lambda: "01900000-0000-7000-8000-00000000000a",
        debug_echo=debug_echo,
        test_numbers=frozenset(listed),
    )
    result = use_case.execute(RequestOtpCommand(phone=phone, locale="fa-AF"))
    return result, sms


class TestAListedNumber:
    def test_gets_its_code_in_the_response(self) -> None:
        result, _ = request(LISTED, listed=(LISTED,))
        assert result.debug_code == "13579"

    def test_costs_nothing(self) -> None:
        """The whole point: no carrier, no charge."""
        _, sms = request(LISTED, listed=(LISTED,))
        assert sms.sent == []


class TestAnUnlistedNumber:
    """The half that matters. Everyone in Ghorband is unlisted."""

    def test_gets_no_code_in_the_response(self) -> None:
        result, _ = request(UNLISTED, listed=(LISTED,))
        assert result.debug_code is None

    def test_still_gets_a_real_message(self) -> None:
        _, sms = request(UNLISTED, listed=(LISTED,))
        assert len(sms.sent) == 1
        assert sms.sent[0]["message_key"] == "auth.sms.otp"

    def test_one_listed_number_does_not_open_the_others(self) -> None:
        """A single entry must not become a wildcard."""
        result, sms = request(UNLISTED, listed=(LISTED, "+93700000903"))
        assert result.debug_code is None
        assert len(sms.sent) == 1


class TestTheDefault:
    @pytest.mark.parametrize("phone", [LISTED, UNLISTED])
    def test_an_empty_list_means_nobody_not_everybody(self, phone: str) -> None:
        """The direction the mistake would go.

        A list that matched anything when unset would silently turn every
        deployment into the thing config.load refuses to start.
        """
        result, sms = request(phone)
        assert result.debug_code is None
        assert len(sms.sent) == 1


def test_debug_echo_still_works_on_its_own() -> None:
    """Development with no list at all is unchanged -- the two features are
    independent, and this is what keeps `scripts/check.sh` honest."""
    result, sms = request(UNLISTED, debug_echo=True)
    assert result.debug_code == "13579"
    assert len(sms.sent) == 1, "debug_echo echoes; it does not stop the send"
