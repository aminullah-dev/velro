"""The inbox, and where a push is sent.

A push is a convenience; the inbox is the record. Everything written here is
readable in the app whether or not any channel managed to deliver it, because
in Ghorband the channel often will not.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import Field

from ui.api import deps
from ui.api.errors import ok
from ui.api.schemas.common import Schema


class RegisterDeviceIn(Schema):
    token: str = Field(min_length=8, max_length=255)
    platform: str = Field(pattern=r"^(ANDROID|IOS|WEB)$")
    app: str = Field(pattern=r"^(PASSENGER|DRIVER)$")
    device_id: str | None = Field(default=None, max_length=128)
    locale: str | None = Field(default=None, max_length=8)


class NotificationOut(Schema):
    id: str
    message_key: str
    payload: dict
    channel: str
    delivery_status: str
    trip_id: str | None
    booking_id: str | None
    created_at: str
    read_at: str | None


class MarkReadIn(Schema):
    # Absent marks everything: the ordinary gesture is opening the screen, not
    # dismissing one message at a time.
    ids: list[str] = Field(default_factory=list)


router = APIRouter(tags=["notifications"])


@router.post("/devices", status_code=201)
def register_device(
    body: RegisterDeviceIn,
    actor: deps.ActorDep,
    tokens: Annotated[object, Depends(deps.device_tokens)],
) -> dict:
    """Where to send a push for this person.

    Upserts on the token, so a shared or reinstalled handset moves to whoever
    is signed in now rather than keeping two owners. Sending a driver's ride
    offer to whoever had the phone last is the failure this prevents.
    """
    row = tokens.register(
        id=deps.new_id(),
        user_id=actor.user_id,
        token=body.token,
        platform=body.platform,
        app=body.app,
        device_id=body.device_id,
        locale=body.locale,
        at=deps.clock().now(),
    )
    return ok({"id": row.id, "app": row.app, "platform": row.platform})


@router.delete("/devices/{token}")
def forget_device(
    token: str,
    actor: deps.ActorDep,
    tokens: Annotated[object, Depends(deps.device_tokens)],
) -> dict:
    """Signing out. A handset that changes hands must stop receiving."""
    rows = [r for r in tokens.for_users([actor.user_id]) if r.token == token]
    removed = tokens.forget(token) if rows else 0
    return ok({"removed": removed})


@router.get("/notifications")
def inbox(
    actor: deps.ActorDep,
    notifications: Annotated[object, Depends(deps.notifications)],
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> dict:
    rows = notifications.for_user(actor.user_id, limit=limit)
    return ok(
        {
            "notifications": [
                NotificationOut(
                    id=r.id,
                    message_key=r.message_key,
                    payload=r.payload or {},
                    channel=r.channel,
                    delivery_status=r.delivery_status,
                    trip_id=r.trip_id,
                    booking_id=r.booking_id,
                    created_at=r.created_at.isoformat() if r.created_at else "",
                    read_at=r.read_at.isoformat() if r.read_at else None,
                ).model_dump()
                for r in rows
            ],
            "unread": notifications.unread_count(actor.user_id),
        }
    )


@router.post("/notifications/read")
def mark_read(
    body: MarkReadIn,
    actor: deps.ActorDep,
    notifications: Annotated[object, Depends(deps.notifications)],
) -> dict:
    marked = notifications.mark_read(
        actor.user_id, at=deps.clock().now(), ids=body.ids
    )
    return ok({"marked": marked, "unread": notifications.unread_count(actor.user_id)})
