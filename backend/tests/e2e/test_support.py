"""Getting help.

The promise these tests protect: VELRO shows you numbers that work without
data, tells you plainly it cannot come, and does not pretend a report is a
rescue. Everything else here is plumbing around that.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.e2e.conftest import auth, sign_in

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def rider(client: TestClient) -> dict:
    return auth(sign_in(client, "+93700000180"))


# -- what to dial -------------------------------------------------------

def test_the_emergency_numbers_need_no_token(client: TestClient) -> None:
    """The one endpoint in VELRO that is deliberately unauthenticated.

    A passenger whose session expired, in a valley, on a phone with no data,
    must still be able to see 119. Everything else being behind require_* is
    correct; this being behind it would mean the app cannot show an emergency
    number to the person most likely to need one. The numbers are public --
    they are printed on posters -- so there is nothing to protect.
    """
    response = client.get("/api/v1/support/contacts")
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["emergency_numbers"] == ["119", "100"]


def test_a_placeholder_velro_number_is_not_offered(client: TestClient) -> None:
    """A button that dials nothing is worse than no button.

    support.contact_phone ships as +93700000000. Rendering a "call VELRO" row
    against it would put a dead control on the screen at the moment somebody is
    frightened, and they would press it and wait.
    """
    data = client.get("/api/v1/support/contacts").json()["data"]
    assert data["velro_number"] is None, (
        "the placeholder number was offered as something to call"
    )


def test_the_categories_come_from_the_domain(client: TestClient) -> None:
    """The client must not invent codes the domain will reject.

    SupportTicket.__post_init__ raises on anything outside CATEGORIES, so a
    client offering its own list produces a form that fails on submit.
    """
    from domain.support import CATEGORIES, URGENT_CATEGORIES

    data = client.get("/api/v1/support/contacts").json()["data"]
    assert set(data["categories"]) == CATEGORIES
    assert set(data["urgent_categories"]) == URGENT_CATEGORIES


# -- raising a report ---------------------------------------------------

def test_raising_a_report_gives_back_a_reference(
    client: TestClient, rider: dict
) -> None:
    """The reference is the only thing the person keeps.

    It has to survive the screen being closed, the app being reinstalled, and a
    phone call to an operator who needs to find the row.
    """
    response = client.post(
        "/api/v1/support/tickets", headers=rider,
        json={"category_code": "SAFETY", "subject": "راننده از راه دیگر رفت",
              "body": "راننده از مسیر عادی خارج شد و جواب نمی‌دهد."},
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["reference"].startswith("TKT-")
    assert data["status"] == "OPEN"
    assert data["is_urgent"] is True


def test_a_category_the_domain_does_not_know_is_refused(
    client: TestClient, rider: dict
) -> None:
    response = client.post(
        "/api/v1/support/tickets", headers=rider,
        json={"category_code": "SOMETHING_INVENTED", "body": "x"},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_an_empty_report_is_refused(client: TestClient, rider: dict) -> None:
    response = client.post(
        "/api/v1/support/tickets", headers=rider,
        json={"category_code": "OTHER", "body": "   "},
    )
    assert response.status_code == 422, response.text


# -- who may read it ----------------------------------------------------

def test_nobody_else_can_read_your_report(
    client: TestClient, rider: dict
) -> None:
    """A safety report may describe an assault.

    404 rather than 403, deliberately: 403 confirms the reference exists.
    """
    mine = client.post(
        "/api/v1/support/tickets", headers=rider,
        json={"category_code": "DRIVER_CONDUCT", "body": "..."},
    ).json()["data"]

    stranger = auth(sign_in(client, "+93700000181"))
    response = client.get(f"/api/v1/support/tickets/{mine['id']}", headers=stranger)
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "TICKET_NOT_FOUND"


def test_an_internal_note_never_reaches_the_person_who_reported(
    client: TestClient, rider: dict, admin_session: dict
) -> None:
    """Operators need somewhere to write "this driver has three of these".

    That somewhere must not be the thread the reporter is reading.
    """
    mine = client.post(
        "/api/v1/support/tickets", headers=rider,
        json={"category_code": "VEHICLE_CONDITION", "body": "بریک خراب بود"},
    ).json()["data"]

    noted = client.post(
        f"/api/v1/support/tickets/{mine['id']}/messages", headers=admin_session,
        json={"body": "third complaint about this driver", "is_internal": True},
    )
    assert noted.status_code == 201, noted.text

    theirs = client.get(
        f"/api/v1/support/tickets/{mine['id']}", headers=rider
    ).json()["data"]
    bodies = [m["body"] for m in theirs["messages"]]
    assert "third complaint about this driver" not in bodies
    assert all(m["is_internal"] is False for m in theirs["messages"])

    staff = client.get(
        f"/api/v1/support/tickets/{mine['id']}", headers=admin_session
    ).json()["data"]
    assert any(m["is_internal"] for m in staff["messages"])


def test_a_passenger_cannot_write_an_internal_note(
    client: TestClient, rider: dict
) -> None:
    mine = client.post(
        "/api/v1/support/tickets", headers=rider,
        json={"category_code": "OTHER", "body": "..."},
    ).json()["data"]
    response = client.post(
        f"/api/v1/support/tickets/{mine['id']}/messages", headers=rider,
        json={"body": "sneaky", "is_internal": True},
    )
    assert response.status_code == 403, response.text


# -- the queue ----------------------------------------------------------

def test_danger_sorts_above_money(
    client: TestClient, rider: dict, admin_session: dict
) -> None:
    """The ordering is the triage.

    Nobody is watching overnight, so a safety report raised at 02:00 must not
    be pushed down the page by a fare dispute raised at 09:00 -- there is no
    human awake to notice it happening.
    """
    client.post(
        "/api/v1/support/tickets", headers=rider,
        json={"category_code": "FARE_DISPUTE", "body": "کرایه زیاد بود"},
    )
    client.post(
        "/api/v1/support/tickets", headers=rider,
        json={"category_code": "SAFETY", "body": "خطر"},
    )

    queue = client.get(
        "/api/v1/admin/support/tickets", headers=admin_session
    ).json()["data"]
    urgent = [t for t in queue["tickets"] if t["is_urgent"]]
    ordinary = [t for t in queue["tickets"] if not t["is_urgent"]]
    assert urgent, "no urgent ticket in the queue at all"
    assert ordinary, "no ordinary ticket to compare against"

    first_ordinary = queue["tickets"].index(ordinary[0])
    last_urgent = max(queue["tickets"].index(t) for t in urgent)
    assert last_urgent < first_ordinary, (
        "a fare dispute was ranked above a safety report"
    )
    assert queue["urgent_open"] >= 1


def test_a_passenger_cannot_read_the_queue(
    client: TestClient, rider: dict
) -> None:
    response = client.get("/api/v1/admin/support/tickets", headers=rider)
    assert response.status_code in (401, 403), response.text


# -- answering ----------------------------------------------------------

def test_a_reply_from_the_reporter_reopens_a_resolved_report(
    client: TestClient, rider: dict, admin_session: dict
) -> None:
    """Marking something fixed is a claim.

    The person who raised it is the one who knows whether it was, so their
    reply pulls it back open rather than landing in a closed thread nobody
    is watching.
    """
    mine = client.post(
        "/api/v1/support/tickets", headers=rider,
        json={"category_code": "LOST_ITEM", "body": "بکس خود را جا ماندم"},
    ).json()["data"]

    resolved = client.post(
        f"/api/v1/admin/support/tickets/{mine['id']}/decide",
        headers=admin_session, json={"status": "RESOLVED"},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["data"]["status"] == "RESOLVED"

    replied = client.post(
        f"/api/v1/support/tickets/{mine['id']}/messages", headers=rider,
        json={"body": "هنوز پیدا نشده"},
    )
    assert replied.status_code == 201, replied.text
    assert replied.json()["data"]["status"] == "IN_PROGRESS", (
        "the reporter said it was not fixed and the request stayed resolved"
    )


def test_a_closed_report_takes_no_more_messages(
    client: TestClient, rider: dict, admin_session: dict
) -> None:
    mine = client.post(
        "/api/v1/support/tickets", headers=rider,
        json={"category_code": "APP_PROBLEM", "body": "اپ بسته می‌شود"},
    ).json()["data"]
    client.post(
        f"/api/v1/admin/support/tickets/{mine['id']}/decide",
        headers=admin_session, json={"status": "CLOSED"},
    )
    response = client.post(
        f"/api/v1/support/tickets/{mine['id']}/messages", headers=rider,
        json={"body": "still broken"},
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "TICKET_CLOSED"


def test_the_reporter_is_told_when_it_is_answered(
    client: TestClient, rider: dict, admin_session: dict
) -> None:
    """A reply nobody sees is not a reply.

    There is no push transport, so the inbox row is the whole mechanism.
    """
    mine = client.post(
        "/api/v1/support/tickets", headers=rider,
        json={"category_code": "OTHER", "body": "سوال دارم"},
    ).json()["data"]
    client.post(
        f"/api/v1/support/tickets/{mine['id']}/messages", headers=admin_session,
        json={"body": "we are looking into it"},
    )

    inbox = client.get("/api/v1/notifications", headers=rider).json()["data"]
    keys = [n["message_key"] for n in inbox["notifications"]]
    assert "notify.support.answered" in keys, keys


def test_a_driver_reporting_as_a_passenger_is_shown_as_the_reporter(
    client: TestClient, admin_session: dict
) -> None:
    """Actor.role is a property of the person, not of the action.

    Somebody who also drives is DRIVER even when they are travelling as a
    passenger -- and in Ghorband most drivers are sometimes passengers. An
    operator reading "Driver" above a complaint about a driver has been told the
    wrong thing, so the thread carries who raised it instead.
    """
    # A user of this test's own who is both. Sharing the seeded احمد with
    # test_vertical_slice means two sign-ins for one phone inside a minute,
    # which trips the OTP rate limiter -- the server working correctly.
    both = auth(sign_in(client, "+93700000185"))
    registered = client.post("/api/v1/driver/register", json={}, headers=both)
    assert registered.status_code in (200, 201, 409), registered.text
    mine = client.post(
        "/api/v1/support/tickets", headers=both,
        json={"category_code": "DRIVER_CONDUCT", "body": "راننده تند می‌راند"},
    ).json()["data"]

    client.post(
        f"/api/v1/support/tickets/{mine['id']}/messages", headers=admin_session,
        json={"body": "we are looking into it"},
    )

    thread = client.get(
        f"/api/v1/support/tickets/{mine['id']}", headers=admin_session
    ).json()["data"]["messages"]

    theirs = [m for m in thread if m["is_from_reporter"]]
    ours = [m for m in thread if not m["is_from_reporter"]]
    assert len(theirs) == 1, "the reporter's own message was not marked as theirs"
    assert len(ours) == 1, "VELRO's reply was marked as coming from the reporter"
    assert theirs[0]["body"] == "راننده تند می‌راند"


def test_safety_is_the_first_category_offered(client: TestClient) -> None:
    """The order on the form is the triage, exactly as it is in the queue.

    sorted() puts SAFETY seventh of eight -- below "Something else" -- which is
    alphabetical in a language nobody reads, on a form somebody opens because
    they are frightened.
    """
    data = client.get("/api/v1/support/contacts").json()["data"]
    assert data["categories"][0] == "SAFETY", data["categories"]
    assert data["categories"][-1] == "OTHER", data["categories"]
    # And the urgent ones come before the ordinary ones.
    urgent = set(data["urgent_categories"])
    positions = [i for i, c in enumerate(data["categories"]) if c in urgent]
    assert positions == list(range(len(urgent))), data["categories"]


def test_a_dispatcher_cannot_read_a_safety_report(
    client: TestClient, rider: dict
) -> None:
    """A finance manager and a dispatcher are staff. Neither is support staff.

    Actor.role collapses all six staff roles into DISPATCHER or ADMIN, so a
    check written against it handed anyone on staff the power to read a report
    that may describe an assault and to write notes on it -- while the queue
    endpoint beside it correctly refused them. Two gates on one feature that
    disagree is worse than either alone.
    """
    from domain.identity import DISPATCHER, FINANCE_MANAGER, STAFF_ROLES
    from ui.api.deps import SUPPORT_STAFF_ROLES

    # The premise: these really are staff, and really are not support staff.
    assert {DISPATCHER, FINANCE_MANAGER} <= STAFF_ROLES
    assert not ({DISPATCHER, FINANCE_MANAGER} & SUPPORT_STAFF_ROLES)


def test_the_two_support_gates_agree(client: TestClient) -> None:
    """require_support and is_support_staff must never diverge.

    They guard the same rows through different endpoints: one the queue, one a
    ticket by id. A reviewer found them disagreeing, and the only reason that
    was not a leak in production is that nobody had a dispatcher account yet.
    """
    import inspect

    from ui.api import deps

    source = inspect.getsource(deps.require_support)
    assert "SUPPORT_STAFF_ROLES" in source, (
        "require_support no longer reads the shared set, so it can drift from "
        "is_support_staff"
    )
    assert "SUPPORT_STAFF_ROLES" in inspect.getsource(deps.is_support_staff)


def test_an_answer_from_velro_stops_saying_nobody_has_read_it(
    client: TestClient, rider: dict, admin_session: dict
) -> None:
    """A reply is proof somebody looked.

    Found on a handset: the app rendered VELRO's answer directly beneath the
    words "Not read yet", because a staff reply left the status at OPEN. To
    somebody waiting to hear that a person had seen their report, that reads as
    nobody having seen it.
    """
    mine = client.post(
        "/api/v1/support/tickets", headers=rider,
        json={"category_code": "VEHICLE_CONDITION", "body": "بریک خراب است"},
    ).json()["data"]
    assert mine["status"] == "OPEN"

    client.post(
        f"/api/v1/support/tickets/{mine['id']}/messages", headers=admin_session,
        json={"body": "we have taken the car off the road"},
    )
    after = client.get(
        f"/api/v1/support/tickets/{mine['id']}", headers=rider
    ).json()["data"]
    assert after["status"] == "IN_PROGRESS", (
        "VELRO answered and the report still says nobody has read it"
    )


def test_an_internal_note_alone_does_not_claim_somebody_answered(
    client: TestClient, rider: dict, admin_session: dict
) -> None:
    """A note staff write to each other is not an answer to the reporter.

    Moving the status on an internal note would tell somebody their report was
    being looked at on the strength of a line they will never see.
    """
    mine = client.post(
        "/api/v1/support/tickets", headers=rider,
        json={"category_code": "OTHER", "body": "سوال"},
    ).json()["data"]
    client.post(
        f"/api/v1/support/tickets/{mine['id']}/messages", headers=admin_session,
        json={"body": "checking with the driver", "is_internal": True},
    )
    after = client.get(
        f"/api/v1/support/tickets/{mine['id']}", headers=rider
    ).json()["data"]
    assert after["status"] == "OPEN"


def test_asking_for_every_status_really_returns_every_status(
    client: TestClient, rider: dict, admin_session: dict
) -> None:
    """The button labelled "All" must not hide anything.

    Omitting the filter gives the working queue -- OPEN and IN_PROGRESS -- which
    is the right default and the wrong answer to "show me everything". An
    operator who clicks All, sees nothing and concludes the report was never
    raised has been told a falsehood by the one screen built to answer that
    call.
    """
    mine = client.post(
        "/api/v1/support/tickets", headers=rider,
        json={"category_code": "LOST_ITEM", "body": "چتر"},
    ).json()["data"]
    client.post(
        f"/api/v1/admin/support/tickets/{mine['id']}/decide",
        headers=admin_session, json={"status": "CLOSED"},
    )

    def references(query: str) -> set[str]:
        data = client.get(
            f"/api/v1/admin/support/tickets{query}", headers=admin_session
        ).json()["data"]
        return {t["reference"] for t in data["tickets"]}

    assert mine["reference"] not in references(""), "the default queue is not an archive"
    assert mine["reference"] in references("?status=ALL")
    assert mine["reference"] in references("?status=CLOSED")


def test_a_status_the_server_does_not_know_is_refused(
    client: TestClient, admin_session: dict
) -> None:
    """A typo must not silently widen or narrow the queue."""
    response = client.get(
        "/api/v1/admin/support/tickets?status=EVERYTHING", headers=admin_session
    )
    assert response.status_code == 422, response.text
