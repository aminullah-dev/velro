"""The privacy page is public, bilingual, and says who to write to."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_the_privacy_page_is_served_to_anyone(client: TestClient) -> None:
    page = client.get("/privacy")
    assert page.status_code == 200, page.text
    assert page.headers["content-type"].startswith("text/html")
    assert "سیاست حریم خصوصی" in page.text
    assert "Privacy Policy" in page.text
    assert "aminhashemi979@gmail.com" in page.text
    assert "{contact}" not in page.text and "{effective}" not in page.text


def test_the_download_page_links_to_it(client: TestClient) -> None:
    page = client.get("/app")
    assert page.status_code == 200
    assert 'href="/privacy"' in page.text


def test_it_says_how_to_delete_an_account_from_inside_the_app(client: TestClient) -> None:
    """The stores link here for "how do I delete my account", and the answer
    must be the button that exists, not a letter to write."""
    page = client.get("/privacy").text
    assert 'id="delete"' in page
    assert "«حذف حساب»" in page
    assert '"Delete account"' in page
