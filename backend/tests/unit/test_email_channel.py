"""The console's own pipe for a sign-in code: an inbox.

The staff are a handful of people opening a laptop, sometimes in a country
where the Roshan SIM is not. For them an email is free where a carrier
charges nearly half a dollar, and it arrives where they are. For everyone
else it does not exist: the handsets never offer it, and a passenger who
somehow asks for it gets an SMS and is told so.

What these hold in place:

  - email carries the code only for a staff account, with an address on
    file, on a deployment that has a mail server, when the server accepts it
  - every other case falls through to SMS and *says* SMS, so the screen
    points at the right place
  - a staff account is never a test number, whatever the list says

No database: this is a decision about which pipe a code goes down.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar

import pytest

from application.use_cases.authenticate import RequestOtp, RequestOtpCommand

STAFF_WITH_INBOX = "+93700000811"
STAFF_NO_INBOX = "+93700000812"
PASSENGER = "+93700000813"


@dataclass
class Row:
    id: str
    status: str = "ACTIVE"
    email: str | None = None


class FakeUsers:
    _BY_PHONE: ClassVar[dict[str, Row]] = {
        STAFF_WITH_INBOX: Row("u-inbox", email="owner@example.org"),
        STAFF_NO_INBOX: Row("u-noinbox"),
        PASSENGER: Row("u-passenger", email="rider@example.org"),
    }
    _ROLES: ClassVar[dict[str, list[str]]] = {
        "u-inbox": ["SUPER_ADMIN"],
        "u-noinbox": ["DISPATCHER"],
        "u-passenger": ["PASSENGER"],
    }

    def find_by_phone(self, phone: str) -> Row | None:
        return self._BY_PHONE.get(phone)

    def roles_of(self, user_id: str) -> list[str]:
        return self._ROLES[user_id]


@dataclass
class FakeOtps:
    rows: list[Any] = field(default_factory=list)

    def count_recent(self, phone: str, *, since: datetime) -> int:
        return 0

    def create(self, **fields: Any) -> Any:
        self.rows.append(fields)
        return fields


class FakeCodes:
    def generate(self, length: int) -> str:
        return "24680"[:length]

    def hash(self, code: str, phone: Any) -> str:
        return f"hashed:{code}"


@dataclass
class FakeSms:
    sent: list[dict[str, Any]] = field(default_factory=list)

    def send(self, **fields: Any) -> bool:
        self.sent.append(fields)
        return True


@dataclass
class FakeEmail:
    accepts: bool = True
    sent: list[dict[str, Any]] = field(default_factory=list)

    def send(self, **fields: Any) -> bool:
        self.sent.append(fields)
        return self.accepts


class FakeSettings:
    def get_int(self, key: str, default: int) -> int:
        return default

    def get_str(self, key: str, default: str = "") -> str:
        return "93" if "country" in key else default


class FrozenClock:
    def now(self) -> datetime:
        return datetime(2026, 9, 2, 9, 0, tzinfo=UTC)


def request(
    phone: str,
    *,
    audience: str = "staff",
    channel: str = "email",
    email: FakeEmail | None = None,
    test_numbers: tuple[str, ...] = (),
):
    sms = FakeSms()
    use_case = RequestOtp(
        users=FakeUsers(), otps=FakeOtps(), codes=FakeCodes(), sms=sms,
        settings=FakeSettings(), clock=FrozenClock(),
        new_id=lambda: "01900000-0000-7000-8000-00000000000c",
        test_numbers=frozenset(test_numbers), email=email,
    )
    result = use_case.execute(
        RequestOtpCommand(phone=phone, locale="fa-AF", audience=audience, channel=channel)
    )
    return result, sms


class TestWhenEmailCarriesIt:
    def test_a_staff_account_with_an_address_gets_the_code_by_email(self) -> None:
        inbox = FakeEmail()
        result, sms = request(STAFF_WITH_INBOX, email=inbox)
        assert result.channel == "email"
        assert sms.sent == [], "no message was paid for"
        assert len(inbox.sent) == 1
        assert inbox.sent[0]["to"] == "owner@example.org"
        assert inbox.sent[0]["payload"]["code"] == "24680"
        assert inbox.sent[0]["locale"] == "fa-AF"

    def test_in_the_language_the_screen_was_set_to(self) -> None:
        inbox = FakeEmail()
        use_case = RequestOtp(
            users=FakeUsers(), otps=FakeOtps(), codes=FakeCodes(), sms=FakeSms(),
            settings=FakeSettings(), clock=FrozenClock(), new_id=lambda: "x", email=inbox,
        )
        use_case.execute(RequestOtpCommand(
            phone=STAFF_WITH_INBOX, locale="en", audience="staff", channel="email",
        ))
        assert inbox.sent[0]["locale"] == "en"


class TestWhenItFallsThroughToSms:
    """Every one of these still puts a code on the phone, and says so."""

    def test_no_address_on_file(self) -> None:
        inbox = FakeEmail()
        result, sms = request(STAFF_NO_INBOX, email=inbox)
        assert result.channel == "sms"
        assert len(sms.sent) == 1
        assert inbox.sent == []

    def test_no_mail_server_on_this_deployment(self) -> None:
        result, sms = request(STAFF_WITH_INBOX, email=None)
        assert result.channel == "sms"
        assert len(sms.sent) == 1

    def test_the_mail_server_refused(self) -> None:
        """A bounced login or a down server must not lock the owner out."""
        inbox = FakeEmail(accepts=False)
        result, sms = request(STAFF_WITH_INBOX, email=inbox)
        assert result.channel == "sms"
        assert len(inbox.sent) == 1, "it was tried"
        assert len(sms.sent) == 1, "and then the carrier carried it"

    def test_staff_who_asked_for_sms_get_sms(self) -> None:
        inbox = FakeEmail()
        result, sms = request(STAFF_WITH_INBOX, channel="sms", email=inbox)
        assert result.channel == "sms"
        assert inbox.sent == []
        assert len(sms.sent) == 1


class TestTheHandsetsNeverGetIt:
    def test_a_passenger_asking_for_email_gets_an_sms(self) -> None:
        """Even with an address on the row: the channel belongs to the console."""
        inbox = FakeEmail()
        result, sms = request(PASSENGER, audience="app", channel="email", email=inbox)
        assert result.channel == "sms"
        assert inbox.sent == []
        assert len(sms.sent) == 1


class TestAStaffAccountIsNeverATestNumber:
    """The seed's +93700000001 sat on OTP_TEST_NUMBERS on the production
    server with SUPER_ADMIN, and two unauthenticated requests were a full
    console takeover. A listed number is handed its code to whoever asks;
    for an account that opens the console that must never happen, whatever
    the list says."""

    def test_the_code_is_sent_for_real_and_never_echoed(self) -> None:
        result, sms = request(
            STAFF_NO_INBOX, channel="sms", test_numbers=(STAFF_NO_INBOX,)
        )
        assert result.debug_code is None
        assert len(sms.sent) == 1

    def test_from_the_app_as_well_as_the_console(self) -> None:
        """The list is consulted on the app path too; the staff check has
        to run there, or the console is simply opened through the app."""
        result, sms = request(
            STAFF_NO_INBOX, audience="app", channel="sms", test_numbers=(STAFF_NO_INBOX,)
        )
        assert result.debug_code is None
        assert len(sms.sent) == 1

    def test_a_passengers_test_handset_still_works(self) -> None:
        """The development convenience stays for the people it is for."""
        result, sms = request(
            PASSENGER, audience="app", channel="sms", test_numbers=(PASSENGER,)
        )
        assert result.debug_code == "24680"
        assert sms.sent == []


@pytest.mark.parametrize("channel", ["email", "sms", "telegram"])
def test_a_refused_console_request_looks_the_same_whatever_the_channel(channel: str) -> None:
    """The silent refusal for non-staff must not leak through the channel
    field either: a stranger asking by email and by SMS gets one answer."""
    inbox = FakeEmail()
    result, sms = request(PASSENGER, audience="staff", channel=channel, email=inbox)
    assert result.channel == "sms"
    assert result.debug_code is None
    assert sms.sent == [] and inbox.sent == []
