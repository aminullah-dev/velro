"""What is published, as var/apks/release.json says.

A module of its own because two very different readers need the same file:
the download doors in routers/app_release.py, and the dashboard, which puts
the newest build beside the builds handsets actually report running. The
dashboard importing a router to read one JSON file is how an import cycle
starts, and two copies of the reader is how the page and the panel end up
disagreeing about what "published" means.

No file, an unreadable file, or a file that is not an object all mean the
same thing: nothing is published. That is this product's state on most days,
so every caller treats it as a normal answer rather than an error.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

#: Runtime artifacts, never in git: scripts/publish-apks.sh drops the APKs
#: and release.json here.
APKS = Path(__file__).resolve().parent.parent.parent / "var" / "apks"

#: The two apps release.json describes, in the order the panel shows them.
APPS = ("passenger", "driver")


def read_release() -> dict[str, Any] | None:
    manifest = APKS / "release.json"
    if not manifest.is_file():
        return None
    try:
        release = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    # A list or a bare string is a half-written publish, not a release. The
    # version answer spreads this into its body, and spreading a list there
    # would turn "nothing published" into a 500 for every handset.
    return release if isinstance(release, dict) else None


def latest_versions() -> dict[str, dict[str, Any] | None]:
    """The newest published build of each app, or None where there is none.

    Only the two numbers an operator compares against what handsets report;
    the APK path and anything else publish-apks.sh adds stay out of it. An
    entry missing a field is treated as unpublished rather than half-shown.
    """
    release = read_release() or {}
    latest: dict[str, dict[str, Any] | None] = {}
    for app in APPS:
        entry = release.get(app)
        try:
            latest[app] = {
                "version_code": int(entry["version_code"]),
                "version_name": str(entry["version_name"]),
            }
        except (TypeError, KeyError, ValueError):
            latest[app] = None
    return latest
