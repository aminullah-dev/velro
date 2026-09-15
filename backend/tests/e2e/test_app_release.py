"""The doors the APK travels through, and the crash inbox.

var/apks is runtime state, so these tests build their own publication in it
and tear it down -- the unpublished answers matter as much as the published
ones, because "nothing is published yet" is this product's state on most
days.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.exc import OperationalError

APKS = Path(__file__).resolve().parent.parent.parent / "var" / "apks"

#: What a 1.2.3 driver build will send on launch.
LAUNCH = {"app": "driver", "version_code": "6", "version_name": "1.2.3", "platform": "android"}


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


# -- which builds are still out there ----------------------------------------

def _session():
    from ui.api import deps

    return deps._session_factory()()


def _counted(**key) -> int:
    """Launches recorded, summed over every day; narrowed by any column given."""
    from infrastructure.db.models.ops import AppVersionCheckRow

    with _session() as session:
        stmt = select(func.coalesce(func.sum(AppVersionCheckRow.checks), 0)).where(
            *(getattr(AppVersionCheckRow, column) == value for column, value in key.items())
        )
        return int(session.scalar(stmt) or 0)


def _without(name: str) -> dict:
    return {k: v for k, v in LAUNCH.items() if k != name}


ODD = {
    "unknown app": {**LAUNCH, "app": "toaster"},
    "unknown platform": {**LAUNCH, "platform": "windows"},
    "shouted platform": {**LAUNCH, "platform": "ANDROID"},
    "code zero": {**LAUNCH, "version_code": "0"},
    "code too big": {**LAUNCH, "version_code": "1000001"},
    "negative code": {**LAUNCH, "version_code": "-6"},
    "code in words": {**LAUNCH, "version_code": "six"},
    "code in Persian digits": {**LAUNCH, "version_code": "۶"},
    "fractional code": {**LAUNCH, "version_code": "6.0"},
    "name too long": {**LAUNCH, "version_name": "1" * 33},
    "name with markup": {**LAUNCH, "version_name": "1.2.3<script>"},
    "name with a space": {**LAUNCH, "version_name": "1.2 3"},
    "empty name": {**LAUNCH, "version_name": ""},
    "no app": _without("app"),
    "no platform": _without("platform"),
    "no code": _without("version_code"),
    "no name": _without("version_name"),
}


class TestVersionChecks:
    """Anonymous launch counts. The answer the handset needs is the point;
    the count must never change it, delay it into an error, or fail it."""

    def test_a_launch_is_counted_and_answered_as_before(self, client: TestClient, published):
        bare = client.get("/api/v1/app/version").json()
        before = _counted(app="driver", platform="android", version_code=6)
        for _ in range(2):
            answer = client.get("/api/v1/app/version", params=LAUNCH)
            assert answer.status_code == 200, answer.text
            assert answer.json() == bare
        assert _counted(app="driver", platform="android", version_code=6) == before + 2

    def test_counted_when_nothing_is_published_too(self, client: TestClient):
        shutil.rmtree(APKS, ignore_errors=True)
        before = _counted(app="driver", version_code=6)
        answer = client.get("/api/v1/app/version", params=LAUNCH)
        assert answer.status_code == 200
        assert answer.json()["data"] == {"available": False}
        assert _counted(app="driver", version_code=6) == before + 1

    @pytest.mark.parametrize("params", list(ODD.values()), ids=list(ODD))
    def test_anything_odd_is_answered_and_not_counted(self, client: TestClient, params: dict):
        bare = client.get("/api/v1/app/version").json()
        before = _counted()
        answer = client.get("/api/v1/app/version", params=params)
        assert answer.status_code == 200, answer.text
        assert answer.json() == bare
        assert _counted() == before

    def test_a_count_that_cannot_be_written_does_not_fail_the_answer(
        self, client: TestClient, published, monkeypatch: pytest.MonkeyPatch
    ):
        from ui.api import deps

        bare = client.get("/api/v1/app/version").json()

        def gone():
            raise OperationalError("INSERT", {}, ConnectionRefusedError("database gone"))

        # The recorder's own session; the request's session is untouched.
        monkeypatch.setattr(deps, "_session_factory", lambda: gone)
        answer = client.get("/api/v1/app/version", params=LAUNCH)
        assert answer.status_code == 200, answer.text
        assert answer.json() == bare

    def test_a_full_day_counts_known_builds_and_drops_invented_ones(self, client: TestClient):
        """Anyone with curl can invent version codes; the day's list is capped."""
        from infrastructure.db.models.ops import AppVersionCheckRow
        from shared.ids import new_id
        from ui.api import deps, opscentre
        from ui.api.routers.app_release import _MAX_BUILDS_PER_DAY

        day_start = opscentre.business_day(deps.clock().now())[0]
        day = day_start.date()
        codes = range(900_000, 900_000 + _MAX_BUILDS_PER_DAY)
        with _session() as session:
            filled = int(session.scalar(
                select(func.count()).select_from(AppVersionCheckRow)
                .where(AppVersionCheckRow.day == day)
            ) or 0)
            for code in list(codes)[filled:]:
                session.add(AppVersionCheckRow(
                    id=new_id(), day=day, app="driver", platform="android",
                    version_code=code, version_name="9.0.0", checks=1,
                    created_at=day_start, updated_at=day_start,
                ))
            session.commit()
        try:
            invented = {**LAUNCH, "version_code": "777777", "version_name": "7.7.7"}
            answer = client.get("/api/v1/app/version", params=invented)
            assert answer.status_code == 200
            assert _counted(version_code=777777) == 0

            known = {**LAUNCH, "version_code": str(codes[-1]), "version_name": "9.0.0"}
            before = _counted(version_code=codes[-1])
            client.get("/api/v1/app/version", params=known)
            assert _counted(version_code=codes[-1]) == before + 1
        finally:
            with _session() as session:
                session.execute(
                    delete(AppVersionCheckRow).where(AppVersionCheckRow.version_code.in_(codes))
                )
                session.commit()

    def test_the_row_keeps_no_time_of_day(self, client: TestClient):
        """Both timestamps are the day's start and stay there: for a build only
        one driver has, a moving updated_at would be his last launch."""
        from infrastructure.db.models.ops import AppVersionCheckRow
        from ui.api import deps, opscentre

        day_start = opscentre.business_day(deps.clock().now())[0]
        launch = {**LAUNCH, "version_code": "555555", "version_name": "5.5.5"}
        try:
            for _ in range(2):
                assert client.get("/api/v1/app/version", params=launch).status_code == 200
            with _session() as session:
                row = session.scalars(
                    select(AppVersionCheckRow).where(AppVersionCheckRow.version_code == 555555)
                ).one()
                assert row.checks == 2
                assert row.created_at == day_start
                assert row.updated_at == day_start
        finally:
            with _session() as session:
                session.execute(
                    delete(AppVersionCheckRow).where(AppVersionCheckRow.version_code == 555555)
                )
                session.commit()


class TestTheDashboardSeesTheBuilds:
    def test_published_beside_launched(
        self, client: TestClient, admin_session: dict, published
    ):
        client.get("/api/v1/app/version", params=LAUNCH)
        client.get(
            "/api/v1/app/version",
            params={**LAUNCH, "version_code": "7", "version_name": "1.2.4"},
        )
        apps = client.get("/api/v1/admin/dashboard", headers=admin_session).json()["data"]["apps"]
        assert apps["window_days"] == 7
        assert apps["latest"] == {
            "passenger": {"version_code": 2, "version_name": "1.0.1"},
            "driver": {"version_code": 2, "version_name": "1.0.1"},
        }
        rows = apps["versions"]
        assert all(
            set(r) == {"app", "platform", "version_code", "version_name", "checks"} for r in rows
        )
        assert rows == sorted(rows, key=lambda r: (r["app"], -r["version_code"], r["platform"]))
        drivers = [r for r in rows if r["app"] == "driver" and r["platform"] == "android"]
        six = next(r for r in drivers if r["version_code"] == 6)
        assert six["version_name"] == "1.2.3"
        assert six["checks"] == _counted(app="driver", platform="android", version_code=6)
        assert [r["version_code"] for r in drivers][:2] == [7, 6]

    def test_nothing_published_is_null_not_missing(
        self, client: TestClient, admin_session: dict
    ):
        shutil.rmtree(APKS, ignore_errors=True)
        apps = client.get("/api/v1/admin/dashboard", headers=admin_session).json()["data"]["apps"]
        assert apps["latest"] == {"passenger": None, "driver": None}

    def test_the_window_is_seven_kabul_days(self, client: TestClient, admin_session: dict):
        """Six days ago is this week; seven days ago is a build nobody is
        running any more as far as the panel is concerned."""
        from infrastructure.db.models.ops import AppVersionCheckRow
        from shared.ids import new_id
        from ui.api.opscentre import KABUL

        today = datetime.now(KABUL).date()
        with _session() as session:
            for code, days_ago in ((900, 6), (901, 7)):
                session.add(AppVersionCheckRow(
                    id=new_id(), day=today - timedelta(days=days_ago), app="passenger",
                    platform="android", version_code=code, version_name=f"0.{code}", checks=3,
                ))
            session.commit()
        try:
            rows = client.get(
                "/api/v1/admin/dashboard", headers=admin_session
            ).json()["data"]["apps"]["versions"]
            codes = {r["version_code"]: r["checks"] for r in rows if r["app"] == "passenger"}
            assert codes.get(900) == 3
            assert 901 not in codes
        finally:
            with _session() as session:
                probes = AppVersionCheckRow.version_code.in_((900, 901))
                session.execute(delete(AppVersionCheckRow).where(probes))
                session.commit()
