"""Authentication endpoints.

A router parses, authorises, calls a use case and serialises. Nothing else. If
one of these functions grows past about fifteen lines it is doing work that
belongs in a use case.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from application.use_cases.authenticate import (
    RefreshSession,
    RefreshSessionCommand,
    RequestOtp,
    RequestOtpCommand,
    VerifyOtp,
    VerifyOtpCommand,
)
from application.use_cases.record_name import RecordName, RecordNameCommand
from domain.enums import ActorRole
from ui.api import deps
from ui.api.errors import ok
from ui.api.schemas.auth import (
    ProfileOut,
    RefreshIn,
    RequestOtpIn,
    SessionOut,
    UpdateProfileIn,
    VerifyOtpIn,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/otp/request")
def request_otp(
    body: RequestOtpIn,
    request: Request,
    users: Annotated[object, Depends(deps.users)],
    otps: Annotated[object, Depends(deps.otps)],
    codes: Annotated[object, Depends(deps.otp_codes)],
    sms: Annotated[object, Depends(deps.sms)],
    settings: Annotated[object, Depends(deps.app_settings)],
) -> dict:
    use_case = RequestOtp(
        users=users, otps=otps, codes=codes, sms=sms, settings=settings,
        clock=deps.clock(), new_id=deps.new_id,
        debug_echo=deps.settings().otp_debug_echo,
        test_numbers=frozenset(deps.settings().otp_test_numbers),
    )
    result = use_case.execute(
        RequestOtpCommand(
            phone=body.phone,
            locale=body.locale,
            request_ip=request.client.host if request.client else None,
        )
    )
    return ok(asdict(result))


@router.post("/otp/verify")
def verify_otp(
    body: VerifyOtpIn,
    request: Request,
    users: Annotated[object, Depends(deps.users)],
    otps: Annotated[object, Depends(deps.otps)],
    refresh_tokens: Annotated[object, Depends(deps.refresh_tokens)],
    codes: Annotated[object, Depends(deps.otp_codes)],
    settings: Annotated[object, Depends(deps.app_settings)],
    audit: Annotated[object, Depends(deps.audit)],
) -> dict:
    cfg = deps.settings()
    use_case = VerifyOtp(
        users=users, otps=otps, refresh_tokens=refresh_tokens, codes=codes,
        tokens=deps.tokens(), settings=settings, audit=audit, clock=deps.clock(),
        new_id=deps.new_id,
        access_ttl_seconds=cfg.jwt_access_ttl_seconds,
        refresh_ttl_seconds=cfg.jwt_refresh_ttl_seconds,
    )
    session = use_case.execute(
        VerifyOtpCommand(
            phone=body.phone,
            code=body.code,
            device_id=body.device_id,
            user_agent=request.headers.get("user-agent"),
            locale=body.locale,
        )
    )
    return ok(SessionOut(**asdict(session)).model_dump())


@router.post("/refresh")
def refresh(
    body: RefreshIn,
    users: Annotated[object, Depends(deps.users)],
    refresh_tokens: Annotated[object, Depends(deps.refresh_tokens)],
) -> dict:
    cfg = deps.settings()
    use_case = RefreshSession(
        users=users, refresh_tokens=refresh_tokens, tokens=deps.tokens(),
        clock=deps.clock(), new_id=deps.new_id,
        access_ttl_seconds=cfg.jwt_access_ttl_seconds,
        refresh_ttl_seconds=cfg.jwt_refresh_ttl_seconds,
    )
    session = use_case.execute(
        RefreshSessionCommand(refresh_token=body.refresh_token, device_id=body.device_id)
    )
    return ok(SessionOut(**asdict(session)).model_dump())


@router.post("/logout-all")
def logout_all_devices(
    actor: deps.ActorDep,
    refresh_tokens: Annotated[object, Depends(deps.refresh_tokens)],
    audit: Annotated[object, Depends(deps.audit)],
) -> dict:
    """Real, not cosmetic: the tokens are server-side and are revoked here."""
    revoked = refresh_tokens.revoke_all_for_user(actor.user_id, at=deps.clock().now())
    audit.write(
        "auth.sessions_revoked",
        actor_id=actor.user_id,
        actor_role=actor.role,
        entity_type="user",
        entity_id=actor.user_id,
        after={"revoked": revoked},
    )
    return ok({"revoked": revoked})


@router.get("/me")
def me(
    actor: deps.ActorDep,
    users: Annotated[object, Depends(deps.users)],
    bookings: Annotated[object, Depends(deps.bookings)],
) -> dict:
    row = users.get(actor.user_id)
    return ok(
        ProfileOut(
            id=row.id, phone=row.phone, full_name=row.full_name,
            locale=row.locale, status=row.status, roles=actor.roles,
            member_since=row.created_at.isoformat() if row.created_at else None,
            completed_trips=bookings.count_completed_for_passenger(row.id),
            rating_average=(
                round(row.rating_sum / row.rating_count, 2)
                if row.rating_count else None
            ),
            rating_count=row.rating_count,
        ).model_dump()
    )


@router.patch("/me")
def update_me(
    body: UpdateProfileIn,
    actor: deps.ActorDep,
    users: Annotated[object, Depends(deps.users)],
    audit: Annotated[object, Depends(deps.audit)],
) -> dict:
    row = users.get(actor.user_id)
    if body.full_name is not None:
        # Through RecordName rather than assigned, so this agrees with the
        # apply form and the approval screen about what a name is. The visible
        # difference: "" now clears the name instead of storing an empty
        # string, which was neither a name nor an absence -- every fallback in
        # the product tests for null, so "" rendered as a blank that no code
        # path knew was blank.
        RecordName(users=users, audit=audit, clock=deps.clock()).execute(
            RecordNameCommand(
                user_id=actor.user_id,
                actor_id=actor.user_id,
                raw_name=body.full_name,
                actor_role=actor.role,
                # Their own account. Nobody else's name is reachable from here.
                allow_overwrite=True,
            )
        )
    if body.locale is not None:
        row.locale = body.locale
    row.updated_by = actor.user_id
    users.save(row)
    return ok(
        ProfileOut(
            id=row.id, phone=row.phone, full_name=row.full_name,
            locale=row.locale, status=row.status, roles=actor.roles,
        ).model_dump()
    )


__all__ = ["ActorRole", "router"]
