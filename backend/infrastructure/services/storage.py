"""File storage.

Driver documents are photographs of a licence, a national identity card and a
vehicle registration. They are the most sensitive data this product holds, so a
few things are non-negotiable and are enforced here rather than left to each
call site:

- The storage key is generated here, never derived from the uploaded filename.
  A name that reaches a path is a directory traversal, and "../../etc" is a
  filename like any other.
- Files are written outside any directory the web server serves. There is no
  URL that reaches them; the only way out is through an endpoint that checks
  who is asking.
- The content type is decided by inspecting the bytes, not by trusting the
  header the client sent.

Local disk today. An object store is a second implementation of the same
protocol and touches nothing above this file.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from shared import error_codes
from shared.errors import InfrastructureError, ValidationError
from shared.ids import new_id

# Only what a phone camera or a scanner produces. A PDF is allowed because a
# vehicle registration often arrives as one.
ALLOWED_TYPES: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}

# Generous for a phone photograph, small enough that an upload cannot fill a
# disk. A driver on a 2G connection will not send more than this anyway.
MAX_FILE_BYTES = 6 * 1024 * 1024

# Magic numbers. The declared content type is a claim by the client; these are
# what the file actually is.
_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"%PDF-", "application/pdf"),
)


@dataclass(frozen=True, slots=True)
class StoredFileContent:
    content: bytes
    content_type: str
    size_bytes: int


def sniff_content_type(content: bytes) -> str | None:
    """The type the bytes actually are, or None if unrecognised."""
    for signature, media_type in _SIGNATURES:
        if content.startswith(signature):
            return media_type
    # WebP: "RIFF" .... "WEBP"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_upload(content: bytes) -> str:
    """Check size and content, and return the type to store it as.

    Raises rather than guessing. A file we cannot identify is not stored: an
    unrecognised upload is either a mistake or an attempt, and neither should
    end up on disk.
    """
    if not content:
        raise ValidationError(error_codes.VALIDATION_FAILED, field="file", reason="empty")
    if len(content) > MAX_FILE_BYTES:
        raise ValidationError(
            error_codes.VALIDATION_FAILED,
            field="file",
            reason="too_large",
            bytes=len(content),
            maximum=MAX_FILE_BYTES,
        )

    actual = sniff_content_type(content)
    if actual is None:
        raise ValidationError(
            error_codes.VALIDATION_FAILED,
            field="file",
            reason="unsupported_type",
            accepted=sorted(ALLOWED_TYPES),
        )
    # The declared type is deliberately not consulted at all. A client can put
    # anything in that header, so the bytes decide and the claim is ignored.
    return actual


class LocalFileStorage:
    """Files under a root directory, sharded by the first two characters of the
    key so a single directory never accumulates tens of thousands of entries."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def put(self, content: bytes, *, content_type: str, namespace: str) -> str:
        if content_type not in ALLOWED_TYPES:
            raise ValidationError(
                error_codes.VALIDATION_FAILED, field="content_type", value=content_type
            )
        # The whole key is generated here. Nothing the uploader sent reaches it.
        identifier = new_id()
        suffix = ALLOWED_TYPES[content_type]
        key = f"{_safe_namespace(namespace)}/{identifier[:2]}/{identifier}{suffix}"

        path = self._path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_bytes(content)
        except OSError as exc:
            raise InfrastructureError(
                error_codes.STORAGE_UNAVAILABLE, reason=type(exc).__name__
            ) from exc
        return key

    def get(self, key: str) -> StoredFileContent:
        path = self._path_for(key)
        if not path.is_file():
            raise InfrastructureError(error_codes.STORAGE_UNAVAILABLE, reason="missing")
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise InfrastructureError(
                error_codes.STORAGE_UNAVAILABLE, reason=type(exc).__name__
            ) from exc
        return StoredFileContent(
            content=content,
            content_type=sniff_content_type(content) or "application/octet-stream",
            size_bytes=len(content),
        )

    def exists(self, key: str) -> bool:
        return self._path_for(key).is_file()

    def delete(self, key: str) -> None:
        path = self._path_for(key)
        if path.is_file():
            path.unlink()

    def _path_for(self, key: str) -> Path:
        """Resolve a key to a path, refusing anything that escapes the root.

        Keys are generated by ``put`` and should always be safe, but this is the
        one place a stored value becomes a filesystem path, so it is checked
        here rather than assumed.
        """
        candidate = (self._root / key).resolve()
        if not candidate.is_relative_to(self._root):
            raise InfrastructureError(error_codes.STORAGE_UNAVAILABLE, reason="path_escape")
        return candidate

    def purge_namespace(self, namespace: str) -> None:
        """Used only by a documented purge job -- see the deletion policy."""
        target = self._root / _safe_namespace(namespace)
        if target.is_dir():
            shutil.rmtree(target)


def _safe_namespace(namespace: str) -> str:
    cleaned = "".join(ch for ch in namespace if ch.isalnum() or ch in "-_")
    if not cleaned:
        raise ValidationError(error_codes.VALIDATION_FAILED, field="namespace")
    return cleaned
