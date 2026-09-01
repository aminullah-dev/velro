"""The operator's workbench pages, served by the product itself.

Only one tool lives here so far: the village placer, which is how 415
villages the public map never heard of get coordinates -- from the person
with the local knowledge, on the product's own map. The page is a public
shell; every request it makes carries the admin's own OTP-earned token, so
serving the HTML reveals nothing and the data doors stay exactly as guarded
as they were.

The MapLibre files are vendored and served from here for the same reason
the tiles are: this must work on a laptop and a phone that share nothing
but a LAN.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse

_ADMIN_DIR = Path(__file__).resolve().parent.parent.parent.parent / "resources" / "admin"

router = APIRouter(tags=["tools"])

_ASSETS = {
    "maplibre-gl.js": "text/javascript",
    "maplibre-gl.css": "text/css",
}


@router.get("/admin/placer", response_class=HTMLResponse)
def placer() -> str:
    return (_ADMIN_DIR / "placer.html").read_text(encoding="utf-8")


@router.get("/admin/placer/assets/{name}")
def asset(name: str) -> FileResponse:
    if name not in _ASSETS:
        from shared import error_codes
        from shared.errors import NotFoundError

        raise NotFoundError(error_codes.VALIDATION_FAILED, file=name)
    return FileResponse(
        _ADMIN_DIR / name,
        media_type=_ASSETS[name],
        headers={"Cache-Control": "public, max-age=86400"},
    )
