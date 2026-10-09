"""An upload that fails must not leave a tazkira on the disk.

A driver's document is written to storage before its row is: the row needs
the key the write produces. When anything after that write failed -- the
audit entry, the flush, the commit itself -- the transaction rolled back and
the row was gone, but the photograph of somebody's identity card stayed in
backend/var with nothing pointing at it: never shown to anyone, never
deleted, never part of an account deletion, because no row names it.

Every failure mode the middleware knows is driven here -- a refusal (4xx), an
exception (500) and a commit that fails after a successful handler -- for
both kinds of document.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.e2e.conftest import JPEG, auth, sign_in

DRIVER = "+93700000583"


@pytest.fixture(scope="module")
def driver(client: TestClient) -> dict:
    session = auth(sign_in(client, DRIVER))
    registered = client.post("/api/v1/driver/register", json={}, headers=session)
    assert registered.status_code in (200, 201), registered.text
    vehicle = client.post(
        "/api/v1/driver/vehicle", headers=session,
        json={"vehicle_type_code": "SEDAN", "plate_number": "ORF-5830"},
    )
    assert vehicle.status_code == 200, vehicle.text
    return {"headers": session, "vehicle_id": vehicle.json()["data"]["id"]}


def _files() -> set[Path]:
    from ui.api import deps

    root = Path(deps.settings().storage_root).resolve()
    return {p for p in root.rglob("*") if p.is_file()}


def _upload(client: TestClient, driver: dict, kind: str):
    if kind == "driver":
        url, code = "/api/v1/driver/documents", "LICENSE"
    else:
        url, code = (
            f"/api/v1/driver/vehicles/{driver['vehicle_id']}/documents",
            "VEHICLE_REGISTRATION",
        )
    return client.post(
        url, headers=driver["headers"],
        files={"file": ("doc.jpg", JPEG, "image/jpeg")},
        data={"document_type_code": code},
    )


def _break_after_storage(monkeypatch, how: str) -> None:
    """Make the request fail after the file is already on disk."""
    from infrastructure.services.audit import SqlAuditLog
    from shared import error_codes
    from shared.errors import ConflictError

    if how == "refusal":
        def write(self, *args, **kwargs):
            raise ConflictError(error_codes.VALIDATION_FAILED, reason="test")
        monkeypatch.setattr(SqlAuditLog, "write", write)
    elif how == "exception":
        def write(self, *args, **kwargs):
            raise RuntimeError("the audit table is on fire")
        monkeypatch.setattr(SqlAuditLog, "write", write)
    else:  # the handler succeeds and the commit does not
        from sqlalchemy.orm import Session

        def commit(self):
            raise RuntimeError("the database went away at commit")
        monkeypatch.setattr(Session, "commit", commit)


@pytest.mark.parametrize("kind", ["driver", "vehicle"])
@pytest.mark.parametrize("how", ["refusal", "exception", "commit"])
def test_a_failed_upload_leaves_no_file_behind(
    client: TestClient, driver: dict, monkeypatch, kind: str, how: str
) -> None:
    before = _files()
    _break_after_storage(monkeypatch, how)
    failed = _upload(client, driver, kind)
    monkeypatch.undo()

    assert failed.status_code >= 400, failed.text
    left = _files() - before
    assert not left, f"a failed {kind} upload ({how}) left {len(left)} file(s) on disk"


@pytest.mark.parametrize("kind", ["driver", "vehicle"])
def test_a_successful_upload_keeps_its_file(
    client: TestClient, driver: dict, kind: str
) -> None:
    before = _files()
    uploaded = _upload(client, driver, kind)
    assert uploaded.status_code == 200, uploaded.text
    assert len(_files() - before) == 1
