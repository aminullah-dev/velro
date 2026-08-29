"""Document validity, shared by every aggregate that holds documents.

A driver holds a licence, a tazkira and a photograph; a vehicle holds its
جواز سیر. The paperwork differs, the rules do not: only the newest upload of a
type counts, a document counts only once someone has verified it, and it stops
counting on the day it runs out.

These live here rather than on `Driver` because the moment they were copied onto
`Vehicle` they would start to drift, and the copy that drifts is the one nobody
is looking at. There is exactly one implementation of "is this paperwork in
order", and both aggregates call it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from domain.enums import DocumentStatus


class HeldDocument(Protocol):
    """What these rules need of a document, and nothing more."""

    document_type_code: str
    status: DocumentStatus
    expires_on: date | None
    uploaded_at: datetime | None


@dataclass(slots=True)
class Document:
    """One uploaded document, belonging to whatever aggregate holds it."""

    id: str
    document_type_code: str
    file_key: str
    status: DocumentStatus = DocumentStatus.PENDING
    expires_on: date | None = None
    verified_by: str | None = None
    verified_at: datetime | None = None
    rejection_reason: str | None = None
    uploaded_at: datetime | None = None

    def is_valid_on(self, on: date) -> bool:
        return is_valid_on(self, on)


def is_valid_on(document: HeldDocument, on: date) -> bool:
    """Verified, and not run out.

    A permit is good *through* its expiry date, not up to it. The mobile apps
    apply the same boundary; if the two disagreed, a driver would be told they
    are fine on the last day and then refused.
    """
    if document.status is not DocumentStatus.VERIFIED:
        return False
    return document.expires_on is None or document.expires_on >= on


def uploaded_after(candidate: HeldDocument, existing: HeldDocument) -> bool:
    """Compare by upload time, falling back to nothing rather than guessing.

    A document with no recorded upload time never displaces one that has one.
    """
    if candidate.uploaded_at is None:
        return False
    if existing.uploaded_at is None:
        return True
    return candidate.uploaded_at > existing.uploaded_at


def newest_of_each_type[D: HeldDocument](documents: list[D]) -> dict[str, D]:
    """The newest upload of each type.

    Only the newest counts. Someone who replaces a licence is presenting the new
    photograph, so the superseded one -- verified though it was -- must not
    satisfy the requirement. Otherwise an administrator could approve a driver
    whose current licence nobody has looked at.
    """
    newest: dict[str, D] = {}
    for document in documents:
        existing = newest.get(document.document_type_code)
        if existing is None or uploaded_after(document, existing):
            newest[document.document_type_code] = document
    return newest


def outstanding(
    documents: list[HeldDocument], required: frozenset[str], *, on: date
) -> frozenset[str]:
    """Required types with no current, verified, unexpired document.

    Note what this does with an empty list: everything required comes back
    outstanding. That is deliberate, and it is what makes the callers fail
    closed -- a caller that forgets to load the documents stops the driver
    rather than waving through someone whose paperwork nobody checked.
    """
    current = newest_of_each_type(documents)
    held = {
        code for code, document in current.items() if is_valid_on(document, on)
    }
    return frozenset(required - held)
