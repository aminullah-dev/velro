"""Signing into the console by email, end to end.

The unit tests prove which pipe a code goes down. This proves the loop
closes: the code that lands in the inbox is the code the server accepts,
and the session it opens carries the staff role. The mail server is a fake
handed to the composition root; everything else is real.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.e2e.conftest import sign_in

pytestmark = pytest.mark.integration

#: A staff number of its own, so this never spends the seeded admin's three
#: requests a minute.
OWNER = "+93700000851"
OWNER_INBOX = "owner-851@example.org"


class Inbox:
    """Where the fake mail server puts what it was given."""

    def __init__(self) -> None:
        self.received: list[dict] = []

    def send(self, **fields) -> bool:
        self.received.append(fields)
        return True


@pytest.fixture(scope="module")
def owner(client: TestClient) -> str:
    """An account opened the ordinary way, given SUPER_ADMIN and an inbox."""
    from infrastructure.db.models.identity import UserRow
    from infrastructure.db.repositories.identity import UserRepository
    from ui.api import deps

    sign_in(client, OWNER)
    with deps._session_factory()() as session:
        user = session.scalars(select(UserRow).where(UserRow.phone == OWNER)).one()
        UserRepository(session).grant_role(user.id, "SUPER_ADMIN")
        user.email = OWNER_INBOX
        session.commit()
    return OWNER


@pytest.fixture()
def inbox(monkeypatch: pytest.MonkeyPatch) -> Inbox:
    from ui.api import deps

    box = Inbox()
    monkeypatch.setattr(deps, "email_sender", lambda: box)
    return box


def test_the_owner_signs_in_with_the_code_from_the_inbox(
    client: TestClient, owner: str, inbox: Inbox
) -> None:
    asked = client.post(
        "/api/v1/auth/otp/request",
        json={"phone": owner, "locale": "fa-AF", "audience": "staff", "channel": "email"},
    )
    assert asked.status_code == 200, asked.text
    answer = asked.json()["data"]
    assert answer["channel"] == "email", "the screen must say where to look"

    [message] = inbox.received
    assert message["to"] == OWNER_INBOX
    code = message["payload"]["code"]
    # The development echo and the inbox agree: one code, one challenge.
    assert answer["debug_code"] == code

    verified = client.post(
        "/api/v1/auth/otp/verify",
        json={"phone": owner, "code": code, "device_id": "laptop", "locale": "fa-AF"},
    )
    assert verified.status_code == 200, verified.text
    assert "SUPER_ADMIN" in verified.json()["data"]["roles"]


def test_without_a_mail_server_the_console_still_opens(
    client: TestClient, owner: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The state every deployment starts in: no SMTP configured. Asking for
    email must not fail -- it must quietly become an SMS and say so."""
    from ui.api import deps

    monkeypatch.setattr(deps, "email_sender", lambda: None)
    asked = client.post(
        "/api/v1/auth/otp/request",
        json={"phone": owner, "locale": "fa-AF", "audience": "staff", "channel": "email"},
    )
    assert asked.status_code == 200, asked.text
    assert asked.json()["data"]["channel"] == "sms"
    assert asked.json()["data"]["debug_code"], "the code still exists; it went by SMS"


def test_a_passenger_cannot_borrow_the_channel(client: TestClient, inbox: Inbox) -> None:
    passenger = "+93700000852"
    sign_in(client, passenger)
    asked = client.post(
        "/api/v1/auth/otp/request",
        json={"phone": passenger, "locale": "fa-AF", "channel": "email"},
    )
    assert asked.status_code == 200, asked.text
    assert asked.json()["data"]["channel"] == "sms"
    assert inbox.received == []
