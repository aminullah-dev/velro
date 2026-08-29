"""The error contract.

One base error, stable machine-readable codes, structured context, and no raw
exception text ever reaching a user. The code is the contract; the wording is
not. Each client resolves a code to a translated key using the same context
dictionary -- one raise site, three languages, three surfaces.
"""

from __future__ import annotations

from typing import Any

from shared.error_codes import is_registered


class AppError(Exception):
    """Base for everything this application raises deliberately."""

    http_status: int = 500

    def __init__(self, code: str, /, **context: Any) -> None:
        if not is_registered(code):
            raise AssertionError(
                f"error code {code!r} is not registered in shared/error_codes.py"
            )
        self.code = code
        self.context: dict[str, Any] = context
        super().__init__(code)

    def __str__(self) -> str:
        if not self.context:
            return self.code
        rendered = ", ".join(f"{k}={v!r}" for k, v in sorted(self.context.items()))
        return f"{self.code} ({rendered})"

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.code!r}, {self.context!r})"


class ValidationError(AppError):
    """Input is malformed."""

    http_status = 422


class NotFoundError(AppError):
    """The entity is absent."""

    http_status = 404


class ConflictError(AppError):
    """State forbids the action."""

    http_status = 409


class PermissionError(AppError):  # noqa: A001 - deliberate: shadows the builtin by design
    """The actor may not do this."""

    http_status = 403


class AuthenticationError(AppError):
    """The actor is not who they claim, or no longer signed in."""

    http_status = 401


class RateLimitError(AppError):
    """Too many attempts."""

    http_status = 429


class IntegrationError(AppError):
    """An external system failed."""

    http_status = 502


class InfrastructureError(AppError):
    """Our own plumbing failed."""

    http_status = 500
