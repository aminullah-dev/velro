"""Master-data import, section 49.

Two steps, never one: **preview** parses the file and reports what it found,
**commit** writes only what the preview said it would plus any duplicate an
operator explicitly confirmed.

The split exists because section 7 forbids merging similar names without proof.
The importer proposes; a person decides. Nothing is deleted, nothing is merged
automatically, and two villages of the same name in different places stay two
records.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import Field

from application.use_cases.import_villages import (
    CommitImportCommand,
    CommitVillageImport,
    PreviewImportCommand,
    PreviewVillageImport,
)
from domain.enums import ImportStatus
from shared import error_codes
from shared.errors import ValidationError
from ui.api import deps
from ui.api.errors import ok
from ui.api.schemas.common import Schema

router = APIRouter(prefix="/admin/imports", tags=["admin"])

# Large enough for every village in Afghanistan several times over, small enough
# that a mistaken upload cannot exhaust memory.
MAX_UPLOAD_BYTES = 8 * 1024 * 1024

ACCEPTED_SUFFIXES = (".csv", ".json", ".xlsx", ".xlsm")


class RowProblemOut(Schema):
    row_number: int
    column: str
    reason: str
    value: str | None = None
    # False when the row is still imported without that field -- a malformed
    # coordinate, for instance.
    blocking: bool = True


class DuplicateProposalOut(Schema):
    row_number: int
    incoming_name: str
    existing_village_id: str | None
    existing_name: str
    score: float
    same_district: bool
    reason: str


class ParsedVillageOut(Schema):
    row_number: int
    district_code: str
    name: str
    aliases: list[str]
    code: str | None = None
    latitude: str | None = None
    longitude: str | None = None


class ImportPreviewOut(Schema):
    job_id: str
    filename: str
    total_rows: int
    valid_rows: int
    problem_count: int
    blocking_count: int
    duplicate_count: int
    will_create_count: int
    problems: list[RowProblemOut]
    duplicates: list[DuplicateProposalOut]
    will_create: list[ParsedVillageOut]


class ImportJobOut(Schema):
    id: str
    entity: str
    filename: str
    status: str
    total_rows: int
    valid_rows: int
    error_rows: int
    duplicate_rows: int
    created_rows: int
    created_at: datetime
    committed_at: datetime | None


class CommitImportIn(Schema):
    # Rows flagged as possible duplicates that a person has confirmed are
    # genuinely different places.
    accept_rows: list[int] = Field(default_factory=list)
    create_stations: bool = True


class CommitImportOut(Schema):
    job_id: str
    villages_created: int
    aliases_created: int
    stations_created: int
    skipped_duplicates: int


@router.post("/villages/preview")
async def preview_village_import(
    actor: Annotated[deps.Actor, Depends(deps.require_operations)],
    jobs: Annotated[object, Depends(deps.import_jobs)],
    villages: Annotated[object, Depends(deps.villages_repo)],
    districts: Annotated[object, Depends(deps.districts_repo)],
    geo: Annotated[object, Depends(deps.geography)],
    audit: Annotated[object, Depends(deps.audit)],
    file: Annotated[UploadFile, File()],
    entity: Annotated[str, Form()] = "villages",
) -> dict:
    """Step one: read the file and report what is in it. Writes no village."""
    filename = (file.filename or "").strip()
    if not filename.lower().endswith(ACCEPTED_SUFFIXES):
        raise ValidationError(
            error_codes.IMPORT_FILE_UNREADABLE,
            reason="unsupported_format",
            filename=filename,
            accepted=list(ACCEPTED_SUFFIXES),
        )

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValidationError(
            error_codes.IMPORT_FILE_UNREADABLE,
            reason="too_large",
            bytes=len(content),
            maximum=MAX_UPLOAD_BYTES,
        )
    if not content:
        raise ValidationError(error_codes.IMPORT_FILE_UNREADABLE, reason="empty")

    use_case = PreviewVillageImport(
        jobs=jobs, villages=villages, districts=districts, geography=geo,
        audit=audit, clock=deps.clock(), new_id=deps.new_id,
    )
    preview = use_case.execute(
        PreviewImportCommand(
            filename=filename,
            content=content,
            actor_id=actor.user_id,
            actor_role=actor.role,
        )
    )

    return ok(
        ImportPreviewOut(
            job_id=preview.job_id,
            filename=filename,
            total_rows=preview.total_rows,
            valid_rows=preview.valid_rows,
            problem_count=len(preview.problems),
            blocking_count=sum(1 for p in preview.problems if p.blocking),
            duplicate_count=len(preview.duplicates),
            will_create_count=len(preview.will_create),
            problems=[RowProblemOut(**asdict(p)) for p in preview.problems],
            duplicates=[DuplicateProposalOut(**asdict(d)) for d in preview.duplicates],
            will_create=[
                ParsedVillageOut(
                    row_number=v.row_number,
                    district_code=v.district_code,
                    name=v.name,
                    aliases=v.aliases,
                    code=v.code,
                    latitude=str(v.latitude) if v.latitude is not None else None,
                    longitude=str(v.longitude) if v.longitude is not None else None,
                )
                for v in preview.will_create
            ],
        ).model_dump()
    )


@router.post("/villages/{job_id}/commit")
def commit_village_import(
    job_id: str,
    body: CommitImportIn,
    actor: Annotated[deps.Actor, Depends(deps.require_operations)],
    jobs: Annotated[object, Depends(deps.import_jobs)],
    villages: Annotated[object, Depends(deps.villages_repo)],
    aliases: Annotated[object, Depends(deps.village_aliases)],
    stations: Annotated[object, Depends(deps.stations_repo)],
    districts: Annotated[object, Depends(deps.districts_repo)],
    geo: Annotated[object, Depends(deps.geography)],
    audit: Annotated[object, Depends(deps.audit)],
) -> dict:
    """Step two: write what the preview said, plus any confirmed duplicates.

    A second call on the same job is refused rather than repeated -- an operator
    who clicks twice on a slow connection must not import everything twice.
    """
    use_case = CommitVillageImport(
        jobs=jobs, villages=villages, aliases=aliases, stations=stations,
        districts=districts, geography=geo, audit=audit,
        clock=deps.clock(), new_id=deps.new_id,
    )
    result = use_case.execute(
        CommitImportCommand(
            job_id=job_id,
            actor_id=actor.user_id,
            actor_role=actor.role,
            accept_rows=tuple(body.accept_rows),
            create_stations=body.create_stations,
        )
    )
    return ok(CommitImportOut(**asdict(result)).model_dump())


@router.get("")
def import_history(
    actor: Annotated[deps.Actor, Depends(deps.require_staff)],
    jobs: Annotated[object, Depends(deps.import_jobs)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict:
    """Past runs. Kept so that "where did this village come from" has an answer."""
    return ok(
        [
            ImportJobOut(
                id=job.id, entity=job.entity, filename=job.filename, status=job.status,
                total_rows=job.total_rows, valid_rows=job.valid_rows,
                error_rows=job.error_rows, duplicate_rows=job.duplicate_rows,
                created_rows=job.created_rows, created_at=job.created_at,
                committed_at=job.committed_at,
            ).model_dump()
            for job in jobs.recent(limit=limit)
        ]
    )


@router.get("/{job_id}")
def import_detail(
    job_id: str,
    actor: Annotated[deps.Actor, Depends(deps.require_staff)],
    jobs: Annotated[object, Depends(deps.import_jobs)],
) -> dict:
    """The stored report for one run, so a preview survives a page reload."""
    job = jobs.get(job_id)
    report = job.report or {}
    return ok(
        {
            "job_id": job.id,
            "filename": job.filename,
            "status": job.status,
            "is_committed": job.status == ImportStatus.COMMITTED.value,
            "total_rows": job.total_rows,
            "valid_rows": job.valid_rows,
            "problem_count": job.error_rows,
            "duplicate_count": job.duplicate_rows,
            "will_create_count": len(report.get("will_create", [])),
            "problems": report.get("problems", []),
            "duplicates": report.get("duplicates", []),
            "will_create": report.get("will_create", []),
        }
    )
