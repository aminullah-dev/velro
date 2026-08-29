"""Driver payouts, section 88.

The rules here are about money, so each one is checked against what the wallet
and the ledger actually hold afterwards, not only against the response body.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.e2e.conftest import auth, sign_in

# Own drivers, so the balances these tests move cannot disturb the vertical
# slice, which asserts on the seeded driver's exact earnings.
PAYEE = "+93700000050"
OTHER = "+93700000051"


@pytest.fixture(scope="module")
def payee(client: TestClient) -> dict:
    return auth(sign_in(client, PAYEE))


@pytest.fixture(scope="module")
def other(client: TestClient) -> dict:
    return auth(sign_in(client, OTHER))


def _become_driver(client: TestClient, headers: dict) -> None:
    client.post("/api/v1/driver/register", json={}, headers=headers)


def _credit(client: TestClient, headers: dict, minor: int) -> None:
    """Put money in the wallet the way a completed trip would.

    Written through the repository rather than by driving a whole trip: these
    tests are about what happens to money once it is there, and a trip per case
    would make them slow and coupled to dispatch.
    """
    from domain.enums import WalletEntryKind
    from infrastructure.db.repositories.money import WalletRepository
    from infrastructure.db.repositories.supply import DriverRepository
    from ui.api import deps

    with deps._session_factory()() as session:
        me = client.get("/api/v1/driver/me", headers=headers).json()["data"]
        wallets = WalletRepository(session)
        DriverRepository(session)
        wallet = wallets.get_or_create(me["id"], "AFN")
        wallets.append(
            wallet=wallet,
            kind=WalletEntryKind.TRIP_EARNING.value,
            amount_minor=minor,
            note="test credit",
        )
        session.commit()


def _earnings(client: TestClient, headers: dict) -> dict:
    r = client.get("/api/v1/driver/earnings", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


# -- reading the balance -------------------------------------------------

def test_a_new_driver_has_an_empty_wallet(client: TestClient, payee: dict) -> None:
    _become_driver(client, payee)
    data = _earnings(client, payee)
    assert data["available"]["amount_minor"] == 0
    assert data["pending"]["amount_minor"] == 0
    assert data["available"]["currency"] == "AFN"


def test_the_ledger_explains_the_balance(client: TestClient, payee: dict) -> None:
    _become_driver(client, payee)
    _credit(client, payee, 120_000)

    r = client.get("/api/v1/driver/earnings/ledger", headers=payee)
    assert r.status_code == 200, r.text
    entries = r.json()["data"]["entries"]
    assert entries, "a credited wallet must show why"
    newest = entries[0]
    assert newest["kind"] == "TRIP_EARNING"
    assert newest["amount"]["amount_minor"] == 120_000
    # Every entry states the balance it produced, so a discrepancy is visible
    # at the row where it first appeared rather than only in the total.
    assert newest["balance_after"]["amount_minor"] == _earnings(client, payee)[
        "available"
    ]["amount_minor"]


def test_the_ledger_pages_without_repeating_an_entry(
    client: TestClient, payee: dict
) -> None:
    _become_driver(client, payee)
    for _ in range(5):
        _credit(client, payee, 1_000)

    first = client.get(
        "/api/v1/driver/earnings/ledger?limit=3", headers=payee
    ).json()["data"]
    assert first["has_more"] is True
    second = client.get(
        f"/api/v1/driver/earnings/ledger?limit=3&offset={first['next_offset']}",
        headers=payee,
    ).json()["data"]

    ids = [e["id"] for e in first["entries"]] + [e["id"] for e in second["entries"]]
    assert len(ids) == len(set(ids)), "a page boundary must not repeat an entry"


# -- requesting a payout -------------------------------------------------

def test_a_payout_moves_money_from_available_to_pending(
    client: TestClient, payee: dict
) -> None:
    _become_driver(client, payee)
    _credit(client, payee, 200_000)
    before = _earnings(client, payee)

    r = client.post(
        "/api/v1/driver/settlements", json={"amount_minor": 80_000}, headers=payee
    )
    assert r.status_code == 201, r.text
    body = r.json()["data"]
    assert body["status"] == "PENDING"
    assert body["reference"].startswith("STL-")
    assert body["amount"]["amount_minor"] == 80_000

    after = _earnings(client, payee)
    assert after["available"]["amount_minor"] == (
        before["available"]["amount_minor"] - 80_000
    )
    assert after["pending"]["amount_minor"] == (
        before["pending"]["amount_minor"] + 80_000
    )
    # Nothing is destroyed by asking for it.
    assert (
        after["available"]["amount_minor"] + after["pending"]["amount_minor"]
        == before["available"]["amount_minor"] + before["pending"]["amount_minor"]
    )


def test_a_second_request_while_one_is_open_is_refused(
    client: TestClient, payee: dict
) -> None:
    _become_driver(client, payee)
    _credit(client, payee, 200_000)
    first = client.post("/api/v1/driver/settlements", json={}, headers=payee)
    assert first.status_code in (201, 409)

    second = client.post(
        "/api/v1/driver/settlements", json={"amount_minor": 60_000}, headers=payee
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "SETTLEMENT_ALREADY_REQUESTED"


def test_a_payout_larger_than_the_balance_is_refused(
    client: TestClient, other: dict
) -> None:
    _become_driver(client, other)
    _credit(client, other, 60_000)

    r = client.post(
        "/api/v1/driver/settlements", json={"amount_minor": 500_000}, headers=other
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "WALLET_INSUFFICIENT_BALANCE"
    # Refused, so nothing moved.
    assert _earnings(client, other)["pending"]["amount_minor"] == 0


def test_a_payout_below_the_minimum_is_refused(client: TestClient, other: dict) -> None:
    _become_driver(client, other)
    _credit(client, other, 60_000)

    r = client.post(
        "/api/v1/driver/settlements", json={"amount_minor": 100}, headers=other
    )
    assert r.status_code == 422
    body = r.json()["error"]
    assert body["code"] == "SETTLEMENT_BELOW_MINIMUM"
    # The context carries the figure, so the app can say how much is needed
    # rather than only that it is not enough.
    assert body["context"]["minimum_minor"] > 0


def test_omitting_the_amount_requests_the_whole_balance(
    client: TestClient, client_driver_factory=None
) -> None:
    session = auth(sign_in(client, "+93700000052"))
    _become_driver(client, session)
    _credit(client, session, 175_000)

    r = client.post("/api/v1/driver/settlements", json={}, headers=session)
    assert r.status_code == 201, r.text
    assert r.json()["data"]["amount"]["amount_minor"] == 175_000
    assert _earnings(client, session)["available"]["amount_minor"] == 0


# -- the office answers --------------------------------------------------

def test_paying_a_settlement_drains_pending_into_lifetime_paid(
    client: TestClient, admin_session: dict
) -> None:
    session = auth(sign_in(client, "+93700000053"))
    _become_driver(client, session)
    _credit(client, session, 300_000)
    created = client.post(
        "/api/v1/driver/settlements", json={"amount_minor": 300_000}, headers=session
    ).json()["data"]

    processing = client.post(
        f"/api/v1/admin/settlements/{created['id']}/decide",
        json={"to": "PROCESSING"},
        headers=admin_session,
    )
    assert processing.status_code == 200, processing.text

    paid = client.post(
        f"/api/v1/admin/settlements/{created['id']}/decide",
        json={"to": "PAID"},
        headers=admin_session,
    )
    assert paid.status_code == 200, paid.text
    assert paid.json()["data"]["paid_at"] is not None

    after = _earnings(client, session)
    assert after["pending"]["amount_minor"] == 0
    assert after["available"]["amount_minor"] == 0
    # The money did not vanish: it moved into the paid total. Asserting only
    # that the buckets emptied would pass even if it had been dropped, which is
    # exactly what an earlier version of this test did.
    assert after["lifetime_paid"]["amount_minor"] == 300_000
    assert after["lifetime_earned"]["amount_minor"] == 300_000


def test_rejecting_a_settlement_gives_the_money_back(
    client: TestClient, admin_session: dict
) -> None:
    session = auth(sign_in(client, "+93700000054"))
    _become_driver(client, session)
    _credit(client, session, 250_000)
    created = client.post(
        "/api/v1/driver/settlements", json={"amount_minor": 250_000}, headers=session
    ).json()["data"]

    rejected = client.post(
        f"/api/v1/admin/settlements/{created['id']}/decide",
        json={"to": "REJECTED", "reason": "بانک نمبر غلط است"},
        headers=admin_session,
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["data"]["rejection_reason"] == "بانک نمبر غلط است"

    after = _earnings(client, session)
    assert after["pending"]["amount_minor"] == 0
    # The driver never lost it, and a refusal is not a payment.
    assert after["available"]["amount_minor"] == 250_000
    assert after["lifetime_paid"]["amount_minor"] == 0

    # And having been given it back, they can ask again.
    again = client.post("/api/v1/driver/settlements", json={}, headers=session)
    assert again.status_code == 201, again.text


def test_a_paid_settlement_cannot_be_paid_twice(
    client: TestClient, admin_session: dict
) -> None:
    session = auth(sign_in(client, "+93700000055"))
    _become_driver(client, session)
    _credit(client, session, 90_000)
    created = client.post("/api/v1/driver/settlements", json={}, headers=session).json()[
        "data"
    ]

    for to in ("PROCESSING", "PAID"):
        r = client.post(
            f"/api/v1/admin/settlements/{created['id']}/decide",
            json={"to": to},
            headers=admin_session,
        )
        assert r.status_code == 200, r.text

    repeat = client.post(
        f"/api/v1/admin/settlements/{created['id']}/decide",
        json={"to": "PAID"},
        headers=admin_session,
    )
    assert repeat.status_code == 409
    assert repeat.json()["error"]["code"] == "SETTLEMENT_INVALID_TRANSITION"

    # The money did not move a second time.
    assert _earnings(client, session)["pending"]["amount_minor"] == 0


def test_a_settlement_cannot_skip_straight_to_paid(
    client: TestClient, admin_session: dict
) -> None:
    session = auth(sign_in(client, "+93700000056"))
    _become_driver(client, session)
    _credit(client, session, 90_000)
    created = client.post("/api/v1/driver/settlements", json={}, headers=session).json()[
        "data"
    ]

    r = client.post(
        f"/api/v1/admin/settlements/{created['id']}/decide",
        json={"to": "PAID"},
        headers=admin_session,
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "SETTLEMENT_INVALID_TRANSITION"


def test_rejecting_without_a_reason_is_refused(
    client: TestClient, admin_session: dict
) -> None:
    session = auth(sign_in(client, "+93700000057"))
    _become_driver(client, session)
    _credit(client, session, 90_000)
    created = client.post("/api/v1/driver/settlements", json={}, headers=session).json()[
        "data"
    ]

    r = client.post(
        f"/api/v1/admin/settlements/{created['id']}/decide",
        json={"to": "REJECTED", "reason": "   "},
        headers=admin_session,
    )
    assert r.status_code == 422
    # And the settlement is untouched, not half-rejected.
    listed = client.get("/api/v1/driver/settlements", headers=session).json()["data"]
    assert listed["settlements"][0]["status"] == "PENDING"


# -- access --------------------------------------------------------------

def test_a_driver_cannot_reach_the_payout_queue(
    client: TestClient, driver_session: dict
) -> None:
    r = client.get("/api/v1/admin/settlements", headers=driver_session)
    assert r.status_code == 403


def test_a_driver_cannot_decide_their_own_payout(client: TestClient) -> None:
    session = auth(sign_in(client, "+93700000058"))
    _become_driver(client, session)
    _credit(client, session, 90_000)
    created = client.post("/api/v1/driver/settlements", json={}, headers=session).json()[
        "data"
    ]

    r = client.post(
        f"/api/v1/admin/settlements/{created['id']}/decide",
        json={"to": "PAID"},
        headers=session,
    )
    assert r.status_code == 403


def test_the_queue_shows_who_is_waiting(
    client: TestClient, admin_session: dict
) -> None:
    r = client.get("/api/v1/admin/settlements", headers=admin_session)
    assert r.status_code == 200, r.text
    rows = r.json()["data"]
    assert rows, "the tests above left payouts open"
    assert all(row["status"] in ("PENDING", "PROCESSING") for row in rows)
    # An operator needs to know who to pay, not just an id.
    assert any(row["driver_phone"] for row in rows)


# -- cash, section 89 ----------------------------------------------------
#
# The passenger pays at the vehicle, so the driver walks away holding the whole
# fare and owing VELRO its share. Every test below is about that direction.

def _owe(client: TestClient, headers: dict, platform_minor: int) -> None:
    """Put a driver in debt the way a completed cash booking does."""
    from infrastructure.db.repositories.money import WalletRepository
    from ui.api import deps

    with deps._session_factory()() as session:
        me = client.get("/api/v1/driver/me", headers=headers).json()["data"]
        wallets = WalletRepository(session)
        wallet = wallets.get_or_create(me["id"], "AFN")
        wallets.record_trip_settlement(
            wallet=wallet,
            platform_minor=platform_minor,
            driver_minor=platform_minor * 9,
            cash=True,
        )
        session.commit()


def test_a_cash_fare_leaves_the_driver_owing_not_owed(client: TestClient) -> None:
    session = auth(sign_in(client, "+93700000070"))
    _become_driver(client, session)
    _owe(client, session, 10_000)

    data = _earnings(client, session)
    assert data["available"]["amount_minor"] == -10_000, "the driver owes the share"
    # What they earned is unaffected by who was holding the notes.
    assert data["lifetime_earned"]["amount_minor"] == 90_000
    assert data["lifetime_commission"]["amount_minor"] == 10_000


def test_the_ledger_records_the_commission_as_a_debit(client: TestClient) -> None:
    session = auth(sign_in(client, "+93700000071"))
    _become_driver(client, session)
    _owe(client, session, 10_000)

    entries = client.get(
        "/api/v1/driver/earnings/ledger", headers=session
    ).json()["data"]["entries"]
    assert entries[0]["kind"] == "COMMISSION"
    assert entries[0]["amount"]["amount_minor"] == -10_000
    assert entries[0]["balance_after"]["amount_minor"] == -10_000


def test_a_driver_in_debt_cannot_request_a_payout(client: TestClient) -> None:
    session = auth(sign_in(client, "+93700000072"))
    _become_driver(client, session)
    _owe(client, session, 60_000)

    r = client.post("/api/v1/driver/settlements", json={}, headers=session)
    assert r.status_code == 409
    body = r.json()["error"]
    # Not "insufficient balance": that would send a driver looking for money
    # that was never theirs to withdraw.
    assert body["code"] == "SETTLEMENT_DIRECTION_INVALID"
    assert body["context"]["owed_minor"] == 60_000


def test_the_app_is_told_which_way_the_money_goes(client: TestClient) -> None:
    session = auth(sign_in(client, "+93700000073"))
    _become_driver(client, session)
    _owe(client, session, 25_000)

    data = client.get("/api/v1/driver/settlements", headers=session).json()["data"]
    assert data["direction"] == "COLLECTION"
    assert data["amount_owed"]["amount_minor"] == 25_000
    assert data["amount_withdrawable"]["amount_minor"] == 0
    assert data["can_request"] is False


def test_recording_a_collection_clears_the_debt_when_paid(
    client: TestClient, admin_session: dict
) -> None:
    session = auth(sign_in(client, "+93700000074"))
    _become_driver(client, session)
    _owe(client, session, 40_000)
    driver_id = client.get("/api/v1/driver/me", headers=session).json()["data"]["id"]

    created = client.post(
        "/api/v1/admin/settlements/collect",
        json={"driver_id": driver_id},
        headers=admin_session,
    )
    assert created.status_code == 201, created.text
    body = created.json()["data"]
    assert body["direction"] == "COLLECTION"
    assert body["amount"]["amount_minor"] == 40_000

    # Held, not cleared: the debt is off the available balance but not yet
    # recognised, so a mistake can still be rejected.
    held = _earnings(client, session)
    assert held["available"]["amount_minor"] == 0
    assert held["pending"]["amount_minor"] == -40_000

    for to in ("PROCESSING", "PAID"):
        r = client.post(
            f"/api/v1/admin/settlements/{body['id']}/decide",
            json={"to": to},
            headers=admin_session,
        )
        assert r.status_code == 200, r.text

    after = _earnings(client, session)
    assert after["available"]["amount_minor"] == 0, "the debt is settled"
    assert after["pending"]["amount_minor"] == 0
    assert after["lifetime_paid"]["amount_minor"] == 40_000


def test_rejecting_a_collection_puts_the_debt_back(
    client: TestClient, admin_session: dict
) -> None:
    session = auth(sign_in(client, "+93700000075"))
    _become_driver(client, session)
    _owe(client, session, 30_000)
    driver_id = client.get("/api/v1/driver/me", headers=session).json()["data"]["id"]

    created = client.post(
        "/api/v1/admin/settlements/collect",
        json={"driver_id": driver_id},
        headers=admin_session,
    ).json()["data"]

    rejected = client.post(
        f"/api/v1/admin/settlements/{created['id']}/decide",
        json={"to": "REJECTED", "reason": "پول کم بود"},
        headers=admin_session,
    )
    assert rejected.status_code == 200, rejected.text

    after = _earnings(client, session)
    # A refused collection restores the debt exactly: VELRO is not owed less
    # because a clerk mistyped.
    assert after["available"]["amount_minor"] == -30_000
    assert after["pending"]["amount_minor"] == 0
    assert after["lifetime_paid"]["amount_minor"] == 0


def test_collecting_more_than_is_owed_is_refused(
    client: TestClient, admin_session: dict
) -> None:
    session = auth(sign_in(client, "+93700000076"))
    _become_driver(client, session)
    _owe(client, session, 20_000)
    driver_id = client.get("/api/v1/driver/me", headers=session).json()["data"]["id"]

    r = client.post(
        "/api/v1/admin/settlements/collect",
        json={"driver_id": driver_id, "amount_minor": 500_000},
        headers=admin_session,
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "SETTLEMENT_AMOUNT_INVALID"
    # Refused, so nothing moved.
    assert _earnings(client, session)["available"]["amount_minor"] == -20_000


def test_a_driver_cannot_record_their_own_collection(client: TestClient) -> None:
    session = auth(sign_in(client, "+93700000077"))
    _become_driver(client, session)
    _owe(client, session, 20_000)
    driver_id = client.get("/api/v1/driver/me", headers=session).json()["data"]["id"]

    r = client.post(
        "/api/v1/admin/settlements/collect",
        json={"driver_id": driver_id},
        headers=session,
    )
    assert r.status_code == 403


def test_the_office_can_see_who_owes(
    client: TestClient, admin_session: dict
) -> None:
    session = auth(sign_in(client, "+93700000078"))
    _become_driver(client, session)
    _owe(client, session, 35_000)
    driver_id = client.get("/api/v1/driver/me", headers=session).json()["data"]["id"]

    r = client.get("/api/v1/admin/settlements/debtors", headers=admin_session)
    assert r.status_code == 200, r.text
    rows = r.json()["data"]
    mine = next(row for row in rows if row["driver_id"] == driver_id)
    # Shown as a positive figure: an operator reads "owes 350", not "-350".
    assert mine["amount_owed"]["amount_minor"] == 35_000
    assert mine["driver_phone"], "an operator needs to know who to ask"
    # Largest debt first -- the working order, not insertion order.
    owed = [row["amount_owed"]["amount_minor"] for row in rows]
    assert owed == sorted(owed, reverse=True)


def test_a_driver_cannot_see_the_debtor_list(
    client: TestClient, driver_session: dict
) -> None:
    r = client.get("/api/v1/admin/settlements/debtors", headers=driver_session)
    assert r.status_code == 403
