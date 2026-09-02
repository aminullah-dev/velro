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
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import Field

from infrastructure.db.models.ops import CrashReportRow
from shared.ids import new_id
from ui.api import deps
from ui.api.errors import ok
from ui.api.schemas.common import Schema

#: The public page and files live at the root, off the API prefix, because
#: "velro.example/app" is what gets said aloud in a bazaar.
page_router = APIRouter(tags=["release"])
router = APIRouter(prefix="/app", tags=["release"])
telemetry_router = APIRouter(prefix="/telemetry", tags=["release"])

_APKS = Path(__file__).resolve().parent.parent.parent.parent / "var" / "apks"
_ALLOWED = {"velro-passenger.apk", "velro-driver.apk"}


def _release() -> dict | None:
    manifest = _APKS / "release.json"
    if not manifest.is_file():
        return None
    try:
        return json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


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


@router.get("/version")
def version() -> dict:
    """What the running apps poll. Absent publication is a normal answer."""
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
