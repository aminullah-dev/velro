"""How the app reaches a handset, and how a dead one reports back.

There is no app store in this product's world: testers and the first real
users sideload an APK. That fact needs three small doors. A human-readable
page (GET /app) that a person standing next to the operator can be pointed
at; the APK files themselves; and a version answer the running app checks so
an old install learns a newer one exists.

What is published lives in var/apks -- runtime artifacts, never in git:
`scripts/publish-apks.sh` builds and drops them there with a release.json
beside. No file there means nothing is published, and every door answers
honestly to that.

The fourth door is the crash inbox. Unauthenticated, because the crash worth
hearing about most is the one before sign-in ever succeeds; capped and
personal-data-free for the same reason.

The version answer also counts, anonymously, which builds are asking -- see
_count_launch for what is kept and, more to the point, what is not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import Field
from sqlalchemy import func, select, update
from sqlalchemy.dialects import postgresql, sqlite

from infrastructure.db.models.ops import AppVersionCheckRow, CrashReportRow
from shared.ids import new_id
from shared.logging import get_logger
from ui.api import deps, opscentre
from ui.api.errors import ok
from ui.api.release_manifest import APKS as _APKS
from ui.api.release_manifest import read_release as _release
from ui.api.schemas.common import Schema

log = get_logger(__name__)

#: The public page and files live at the root, off the API prefix, because
#: "velro.example/app" is what gets said aloud in a bazaar.
page_router = APIRouter(tags=["release"])
router = APIRouter(prefix="/app", tags=["release"])
telemetry_router = APIRouter(prefix="/telemetry", tags=["release"])

_ALLOWED = {"velro-passenger.apk", "velro-driver.apk"}


_PAGE = """<!doctype html>
<html dir="rtl" lang="fa">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ولرو</title>
<style>
 body {{ font-family: system-ui, sans-serif; background: #0e4d3c; color: #fff;
        margin: 0; padding: 2rem 1.25rem; text-align: center; }}
 h1 {{ font-size: 2.4rem; margin: 1rem 0 0.25rem; }}
 p  {{ color: #cfe4dc; margin: 0.25rem 0 2rem; }}
 a.button {{ display: block; background: #f5c400; color: #1c1b16;
        border-radius: 999px; padding: 1rem; margin: 0.8rem auto; max-width: 22rem;
        font-weight: 700; text-decoration: none; font-size: 1.15rem; }}
 .muted {{ color: #9dbdb2; font-size: 0.85rem; margin-top: 2.5rem; }}
</style>
</head>
<body>
<h1>ولرو</h1>
<p>چوکی رزرو کنید. با اطمینان سفر کنید.<br>څوکۍ خوندي کړئ. ډاډمن سفر وکړئ.</p>
{buttons}
<p class="muted">نسخه {version} · پس از دانلود، نصب از «منابع نامعلوم» را اجازه دهید<br>
له ښکته کولو وروسته د «نامعلومو سرچینو» نصب ته اجازه ورکړئ</p>
<p class="muted"><a href="/privacy" style="color:#9dbdb2">سیاست حریم خصوصی · Privacy policy</a></p>
</body>
</html>"""


@page_router.get("/app", response_class=HTMLResponse)
def download_page() -> str:
    release = _release()
    if release is None:
        return _PAGE.format(
            buttons='<p style="color:#f5c400">هنوز نسخه‌ای منتشر نشده است.<br>'
                    "تر اوسه کومه بڼه نه ده خپره شوې.</p>",
            version="—",
        )
    buttons = (
        '<a class="button" href="/app/velro-passenger.apk">📱 اپ مسافر — د مسافر اپ</a>'
        '<a class="button" href="/app/velro-driver.apk">🚕 اپ راننده — د چلوونکي اپ</a>'
    )
    return _PAGE.format(
        buttons=buttons, version=release["passenger"]["version_name"]
    )


@page_router.get("/app/{filename}")
def apk(filename: str) -> FileResponse:
    # The allow-list IS the path check: nothing a client sends becomes a path.
    if filename not in _ALLOWED:
        from shared import error_codes
        from shared.errors import NotFoundError

        raise NotFoundError(error_codes.VALIDATION_FAILED, file=filename)
    path = _APKS / filename
    if not path.is_file():
        from shared import error_codes
        from shared.errors import NotFoundError

        raise NotFoundError(error_codes.VALIDATION_FAILED, file=filename)
    return FileResponse(
        path,
        media_type="application/vnd.android.package-archive",
        filename=filename,
    )


#: What a launch may say about itself. Strict on purpose: the values go
#: straight into a table that nobody signs in to write to, so anything that is
#: not plainly a version is not counted at all. [0-9] rather than \d, because
#: \d and int() both accept Persian and Arabic-Indic digits, and "۷" is not a
#: version code any build of these apps will ever send.
_APPS = frozenset({"passenger", "driver"})
_PLATFORMS = frozenset({"android", "ios"})
_VERSION_CODE = re.compile(r"[0-9]{1,7}")
_VERSION_NAME = re.compile(r"[0-9A-Za-z.+-]{1,32}")
_MAX_VERSION_CODE = 1_000_000
#: New builds a single day may add. Two apps ever report a handful of builds
#: each; past this the day's table is full of invented codes, and a new code
#: is dropped while every build already on the list is still counted. Without
#: it, anyone with curl could add a row per code per day, unbounded.
_MAX_BUILDS_PER_DAY = 100


@dataclass(frozen=True, slots=True)
class _Launch:
    app: str
    platform: str
    version_code: int
    version_name: str


def _launch(
    app: str | None, platform: str | None, version_code: str | None, version_name: str | None
) -> _Launch | None:
    """The launch these parameters describe, or None if they describe nothing.

    All four or none: a count keyed on a version with half its identity
    missing is a count nobody can act on.
    """
    if app not in _APPS or platform not in _PLATFORMS:
        return None
    if version_code is None or not _VERSION_CODE.fullmatch(version_code):
        return None
    code = int(version_code)
    if not 1 <= code <= _MAX_VERSION_CODE:
        return None
    if version_name is None or not _VERSION_NAME.fullmatch(version_name):
        return None
    return _Launch(app=app, platform=platform, version_code=code, version_name=version_name)


def _count_launch(launch: _Launch) -> None:
    """Add one to today's counter for this build. Never raises.

    Anonymous by construction: the row is (Kabul day, app, platform, version)
    and a number. No user id -- the endpoint has no sign-in, and must not grow
    one for this. No IP address and no device id either: either would turn a
    count of launches into a record of who opened the app when, and the only
    question this exists to answer is which builds are still out there. It
    counts launches; it does not follow people.

    Its own session, committed here, rather than the request's: the answer
    the handset is waiting for must not depend on this write. If PostgreSQL
    is down or the table is missing, the old app still learns a new one
    exists -- the count is a nicety, the update prompt is the point. A write
    that shared the request's transaction would fail the whole response on a
    commit error, which is exactly the failure this must not cause.
    """
    # The day's start stands in for both timestamps, and neither moves again:
    # an updated_at that followed each launch would be, for a build only one
    # driver has, that driver's last launch to the second.
    day_start = opscentre.business_day(deps.clock().now())[0]
    day = day_start.date()
    checks = AppVersionCheckRow
    try:
        with deps._session_factory()() as session:
            full = (
                session.scalar(
                    select(func.count()).select_from(checks).where(checks.day == day)
                )
                or 0
            ) >= _MAX_BUILDS_PER_DAY
            if full:
                # Builds already on today's list keep counting; a new one waits
                # for tomorrow. A real build is on the list long before a day
                # fills, so what is dropped here is invented codes.
                session.execute(
                    update(checks)
                    .where(
                        checks.day == day,
                        checks.app == launch.app,
                        checks.platform == launch.platform,
                        checks.version_code == launch.version_code,
                    )
                    .values(checks=checks.checks + 1)
                )
                session.commit()
                return
            # ON CONFLICT exists in both dialects the schema is written for,
            # under the same name; the two constructs differ only in import.
            dialect = session.get_bind().dialect.name
            insert = postgresql.insert if dialect == "postgresql" else sqlite.insert
            stmt = insert(checks).values(
                id=new_id(),
                day=day,
                app=launch.app,
                platform=launch.platform,
                version_code=launch.version_code,
                version_name=launch.version_name,
                checks=1,
                created_at=day_start,
                updated_at=day_start,
            )
            # One statement, not read-then-write: two handsets launching the
            # same build in the same second must both be counted, and neither
            # may fail on the unique key. version_name is left as first seen.
            stmt = stmt.on_conflict_do_update(
                index_elements=["day", "app", "platform", "version_code"],
                set_={"checks": checks.checks + 1},
            )
            session.execute(stmt)
            session.commit()
    except Exception as exc:
        log.warning(
            "app.version_check_not_counted",
            app=launch.app,
            version_code=launch.version_code,
            error=type(exc).__name__,
        )


@router.get("/version")
def version(
    app: str | None = None,
    platform: str | None = None,
    version_code: str | None = None,
    version_name: str | None = None,
) -> dict:
    """What the running apps poll. Absent publication is a normal answer.

    The four parameters are how a build says which one it is; every one is
    optional, and the builds in people's hands today send none of them.
    Declared as plain strings and checked by hand rather than typed for
    FastAPI, because a typed parameter that fails validation answers 422 --
    and a handset that sent something odd must still hear about the update.
    Whatever they say, the answer below is the same.
    """
    launch = _launch(app, platform, version_code, version_name)
    if launch is not None:
        _count_launch(launch)
    release = _release()
    if release is None:
        return ok({"available": False})
    return ok({"available": True, **release})


class CrashIn(Schema):
    app: str = Field(pattern=r"^(passenger|driver)$")
    version_code: int = Field(ge=1, le=1_000_000)
    version_name: str = Field(max_length=40)
    device: str = Field(max_length=120)
    sdk: int = Field(ge=1, le=200)
    #: Capped hard: a stack trace tells its story in its first hundred lines.
    stack: str = Field(max_length=16_000)
    occurred_at: datetime


@telemetry_router.post("/crash", status_code=201)
def report_crash(body: CrashIn, session: deps.SessionDep) -> dict:
    session.add(CrashReportRow(
        id=new_id(),
        app=body.app,
        version_code=body.version_code,
        version_name=body.version_name,
        device=body.device,
        sdk=body.sdk,
        stack=body.stack,
        occurred_at=body.occurred_at,
        received_at=datetime.now(UTC),
    ))
    return ok({"received": True})
