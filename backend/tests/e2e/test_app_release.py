"""The doors the APK travels through, and the crash inbox.

var/apks is runtime state, so these tests build their own publication in it
and tear it down -- the unpublished answers matter as much as the published
ones, because "nothing is published yet" is this product's state on most
days.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

APKS = Path(__file__).resolve().parent.parent.parent / "var" / "apks"


@pytest.fixture()
def published():
    APKS.mkdir(parents=True, exist_ok=True)
    (APKS / "velro-passenger.apk").write_bytes(b"not-really-an-apk")
    (APKS / "velro-driver.apk").write_bytes(b"also-not")
    (APKS / "release.json").write_text(json.dumps({
        "passenger": {"version_name": "1.0.1", "version_code": 2,
                      "apk": "/app/velro-passenger.apk"},
        "driver": {"version_name": "1.0.1", "version_code": 2,
                   "apk": "/app/velro-driver.apk"},
    }), encoding="utf-8")
    yield
    shutil.rmtree(APKS, ignore_errors=True)


class TestUnpublished:
    def test_the_page_says_so_in_both_languages(self, client: TestClient):
        shutil.rmtree(APKS, ignore_errors=True)
        page = client.get("/app")
        assert page.status_code == 200
        assert "هنوز نسخه‌ای منتشر نشده" in page.text
        assert "نه ده خپره شوې" in page.text

    def test_the_version_answer_is_calm(self, client: TestClient):
        shutil.rmtree(APKS, ignore_errors=True)
        answer = client.get("/api/v1/app/version")
        assert answer.status_code == 200
        assert answer.json()["data"] == {"available": False}


class TestPublished:
    def test_the_page_offers_both_apps(self, client: TestClient, published):
        page = client.get("/app")
        assert "velro-passenger.apk" in page.text
        assert "velro-driver.apk" in page.text
        assert "1.0.1" in page.text

    def test_the_apk_arrives_with_the_installable_type(
        self, client: TestClient, published
    ):
        apk = client.get("/app/velro-passenger.apk")
        assert apk.status_code == 200
        assert apk.headers["content-type"] == "application/vnd.android.package-archive"
        assert apk.content == b"not-really-an-apk"

    def test_the_version_answer_names_the_newer_build(
        self, client: TestClient, published
    ):
        data = client.get("/api/v1/app/version").json()["data"]
        assert data["available"] is True
        assert data["passenger"]["version_code"] == 2

    def test_only_the_two_named_files_exist(self, client: TestClient, published):
        for sneaky in ("release.json", "..%2Frelease.json", "x.apk"):
            assert client.get(f"/app/{sneaky}").status_code in (404, 422)


class TestCrashInbox:
    def _crash(self, **overrides):
        body = {
            "app": "passenger", "version_code": 1, "version_name": "1.0.0",
            "device": "SM-A225F", "sdk": 33,
            "stack": "java.lang.IllegalStateException: boom\\n\\tat af.velro...",
            "occurred_at": datetime.now(UTC).isoformat(),
        }
        body.update(overrides)
        return body

    def test_a_dying_handset_needs_no_credentials(self, client: TestClient):
        landed = client.post("/api/v1/telemetry/crash", json=self._crash())
        assert landed.status_code == 201, landed.text

    def test_the_operator_reads_it_back(self, client: TestClient, admin_session: dict):
        client.post("/api/v1/telemetry/crash", json=self._crash(device="read-back-probe"))
        rows = client.get("/api/v1/admin/crashes", headers=admin_session).json()["data"]
        assert any(r["device"] == "read-back-probe" for r in rows)
        assert "boom" in rows[0]["stack"]

    def test_a_novel_sized_stack_is_refused_not_stored(self, client: TestClient):
        refused = client.post(
            "/api/v1/telemetry/crash", json=self._crash(stack="x" * 20_000)
        )
        assert refused.status_code == 422

    def test_a_made_up_app_name_is_refused(self, client: TestClient):
        refused = client.post(
            "/api/v1/telemetry/crash", json=self._crash(app="toaster")
        )
        assert refused.status_code == 422

    def test_a_passenger_cannot_read_the_inbox(
        self, client: TestClient, passenger_session: dict
    ):
        refused = client.get("/api/v1/admin/crashes", headers=passenger_session)
        assert refused.status_code == 403
