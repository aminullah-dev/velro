from __future__ import annotations

from pydantic import Field

from ui.api.schemas.common import Schema


class RequestOtpIn(Schema):
    phone: str = Field(min_length=6, max_length=24, examples=["0700123456"])
    locale: str = Field(default="fa-AF", pattern=r"^(en|fa-AF|ps)$")


class RequestOtpOut(Schema):
    expires_in_seconds: int
    resend_after_seconds: int
    # Present only when the deployment enables it. Never in production.
    debug_code: str | None = None


class VerifyOtpIn(Schema):
    phone: str = Field(min_length=6, max_length=24)
    code: str = Field(min_length=4, max_length=8)
    device_id: str | None = Field(default=None, max_length=128)
    locale: str = Field(default="fa-AF", pattern=r"^(en|fa-AF|ps)$")


class RefreshIn(Schema):
    refresh_token: str = Field(min_length=16)
    device_id: str | None = Field(default=None, max_length=128)


class SessionOut(Schema):
    user_id: str
    access_token: str
    refresh_token: str
    roles: list[str]
    is_new_user: bool
    expires_in_seconds: int


class ProfileOut(Schema):
    id: str
    phone: str
    full_name: str | None
    locale: str
    status: str
    roles: list[str]
    #: When the account was opened. The passenger's own profile says how long
    #: they have been travelling with VELRO, and there is nowhere else to get
    #: it from -- the app never sees the users table.
    member_since: str | None = None
    #: Journeys actually taken, not booked. A count that includes cancellations
    #: flatters the number and means nothing to the person reading it.
    completed_trips: int = 0
    #: What drivers have scored this passenger, or null before anybody has.
    #: Null rather than 0.0, which reads as a bad score rather than no score.
    rating_average: float | None = None
    rating_count: int = 0


class UpdateProfileIn(Schema):
    full_name: str | None = Field(default=None, max_length=160)
    locale: str | None = Field(default=None, pattern=r"^(en|fa-AF|ps)$")
