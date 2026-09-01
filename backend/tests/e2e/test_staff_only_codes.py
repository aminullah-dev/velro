"""The operator console's sign-in screen, over the real API.

Before this, the console posted to the same public endpoint the handsets post
to and said nothing about being the console. So the admin sign-in form was a
free SMS button pointed at any number in Afghanistan, drawn against a budget
of roughly a hundred messages a month.

The unit tests next door prove the decision. These prove the wiring: that the
console's request actually carries `audience`, that the server acts on it, and
-- the one that matters most on the morning this ships -- that the person who
runs VELRO can still get in.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

pytestmark = pytest.mark.integration

#: The seeded super administrator.
ADMIN = "+93700000001"
#: A number of its own, so the console tests never spend the admin's three
#: requests a minute.
STAFF_UNDER_TEST = "+93700000841"
PASSENGER = "+93700000842"
NEVER_SEEN = "+93700000843"


def _ask(client: TestClient, phone: str, *, audience: str | None = None):
    body: dict[str, str] = {"phone": phone, "locale": "fa-AF"}
    if audience is not None:
        body["audience"] = audience
    return client.post("/api/v1/auth/otp/request", json=body)


def _session():
    from ui.api import deps

    return deps._session_factory()()


@pytest.fixture(scope="module")
def a_staff_number(client: TestClient) -> str:
    """Open an account the ordinary way, then give it a desk."""
    from infrastructure.db.models.identity import UserRow
    from tests.e2e.conftest import sign_in

    sign_in(client, STAFF_UNDER_TEST)
    with _session() as session:
        user = session.scalars(
            select(UserRow).where(UserRow.phone == STAFF_UNDER_TEST)
        ).one()
        from infrastructure.db.repositories.identity import UserRepository

        UserRepository(session).grant_role(user.id, "SUPPORT_AGENT")
        session.commit()
    return STAFF_UNDER_TEST


class TestTheDoorStillOpens:
    """Run these first in your head before shipping. A console nobody can
    reach is a worse outcome than the problem being fixed."""

    def test_a_staff_number_still_receives_a_console_code(
        self, client: TestClient, a_staff_number: str
    ) -> None:
        answer = _ask(client, a_staff_number, audience="staff")
        assert answer.status_code == 200, answer.text
        assert answer.json()["data"]["debug_code"], (
            "a staff number asked the console for a code and got none -- "
            "this is the whole operator locked out of their own service"
        )

    def test_the_seeded_administrator_is_staff_enough(self, client: TestClient) -> None:
        """SUPER_ADMIN counts. It would be a poor joke if it did not."""
        answer = _ask(client, ADMIN, audience="staff")
        assert answer.status_code == 200, answer.text
        assert answer.json()["data"]["debug_code"]


class TestTheDoorIsShutToEveryoneElse:
    def test_a_passenger_gets_no_console_code(self, client: TestClient) -> None:
        from tests.e2e.conftest import sign_in

        sign_in(client, PASSENGER)          # a real account, no staff role
        answer = _ask(client, PASSENGER, audience="staff")
        assert answer.status_code == 200, answer.text
        assert answer.json()["data"]["debug_code"] is None

    def test_a_number_with_no_account_gets_no_console_code(
        self, client: TestClient
    ) -> None:
        answer = _ask(client, NEVER_SEEN, audience="staff")
        assert answer.status_code == 200, answer.text
        assert answer.json()["data"]["debug_code"] is None

    def test_refusal_looks_exactly_like_success(self, client: TestClient) -> None:
        """Otherwise the sign-in form becomes a staff directory: type numbers,
        read the answers, learn whose handset opens the console."""
        refused = _ask(client, NEVER_SEEN, audience="staff")
        assert refused.status_code == 200
        body = refused.json()["data"]
        assert set(body) == {
            "expires_in_seconds",
            "resend_after_seconds",
            "debug_code",
            "channel",
        }
        assert body["expires_in_seconds"] > 0
        assert body["resend_after_seconds"] > 0


class TestTheHandsetsAreUntouched:
    def test_a_passenger_still_signs_in_from_the_app(self, client: TestClient) -> None:
        """The failure mode that would matter most: shipping the console's
        lock onto every phone in Ghorband."""
        answer = _ask(client, NEVER_SEEN)
        assert answer.status_code == 200, answer.text
        assert answer.json()["data"]["debug_code"], (
            "the app's own sign-in must be unchanged -- anybody may open an "
            "account, that is the product"
        )

    def test_an_audience_nobody_offers_is_refused_not_guessed(
        self, client: TestClient
    ) -> None:
        answer = _ask(client, NEVER_SEEN, audience="root")
        assert answer.status_code == 422, answer.text
