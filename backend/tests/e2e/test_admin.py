"""Admin panel endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_the_route_list_shows_the_price_in_force_not_the_cheapest(
    client: TestClient, admin_session: dict
) -> None:
    """Superseding a price closes the old rule and opens a new one, so both
    rows exist. The list showed whichever was cheapest, which meant a raised
    price never appeared and an operator raised it again and again.
    """
    routes = client.get("/api/v1/admin/routes?limit=1", headers=admin_session)
    assert routes.status_code == 200, routes.text
    route = routes.json()["data"][0]
    before = route["fare_minor"]
    assert before is not None, "the seed prices every route"

    raised = before + 25_000
    changed = client.post(
        f"/api/v1/admin/routes/{route['id']}/fare",
        json={"amount_minor": raised},
        headers=admin_session,
    )
    assert changed.status_code == 200, changed.text

    again = client.get("/api/v1/admin/routes?limit=1", headers=admin_session).json()["data"][0]
    assert again["id"] == route["id"]
    assert again["fare_minor"] == raised, "the list must show the new price"

    # And lowering it works too -- a fix that only handled increases would pass
    # the test above while still reading the wrong row.
    lowered = before - 5_000
    client.post(
        f"/api/v1/admin/routes/{route['id']}/fare",
        json={"amount_minor": lowered},
        headers=admin_session,
    )
    final = client.get("/api/v1/admin/routes?limit=1", headers=admin_session).json()["data"][0]
    assert final["fare_minor"] == lowered
