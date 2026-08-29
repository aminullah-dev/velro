"""The audit trail.

Append-only, never rotated, included in backups, admissible in a dispute.
Written inside the same transaction as the change it records: an audit trail
that can be missing when the write succeeded is worse than none, because it
will be trusted.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from domain.enums import ActorRole
from infrastructure.db.models.ops import AuditLogRow
from shared.clock import Clock
from shared.ids import new_id
from shared.logging import redact

# Fields that must never be written into an audit diff.
_NEVER_RECORD = frozenset(
    {"verification_code", "code_hash", "token_hash", "password", "otp", "qr_payload"}
)


class SqlAuditLog:
    def __init__(self, session: Session, clock: Clock) -> None:
        self._session = session
        self._clock = clock

    def write(
        self,
        action: str,
        *,
        actor_id: str | None,
        actor_role: ActorRole,
        entity_type: str,
        entity_id: str,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        origin: str = "api",
        request_id: str | None = None,
        ip_address: str | None = None,
    ) -> None:
        self._session.add(
            AuditLogRow(
                id=new_id(),
                occurred_at=self._clock.now(),
                actor_id=actor_id,
                actor_role=actor_role.value,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                before=_clean(before),
                after=_clean(after),
                origin=origin,
                request_id=request_id,
                ip_address=ip_address,
            )
        )


def _clean(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    return redact({k: v for k, v in payload.items() if k not in _NEVER_RECORD})


def diff(before: dict[str, Any], after: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Only the changed fields, so an audit row stays readable years later."""
    changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
    return ({k: before.get(k) for k in changed}, {k: after.get(k) for k in changed})
