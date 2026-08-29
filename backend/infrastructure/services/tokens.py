"""Access and refresh tokens.

Short-lived JWT for access, opaque rotating token for refresh. The refresh
token is stored server-side as a hash and is revocable, which is what makes
'log out all devices' a real operation rather than a client-side gesture.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from typing import Any

from jose import JWTError, jwt

from shared import error_codes
from shared.errors import AuthenticationError

_ALGORITHM = "HS256"


class JwtTokenService:
    def __init__(self, secret: str, *, issuer: str = "velro") -> None:
        if len(secret) < 32:
            raise ValueError("jwt secret must be at least 32 characters")
        self._secret = secret
        self._issuer = issuer

    def issue_access_token(
        self, *, user_id: str, roles: list[str], expires_at: datetime
    ) -> str:
        payload = {
            "sub": user_id,
            "roles": roles,
            "iss": self._issuer,
            "exp": int(expires_at.timestamp()),
            "iat": int(datetime.now(UTC).timestamp()),
        }
        return jwt.encode(payload, self._secret, algorithm=_ALGORITHM)

    def read_access_token(self, token: str) -> dict[str, Any]:
        try:
            return jwt.decode(
                token, self._secret, algorithms=[_ALGORITHM], issuer=self._issuer
            )
        except JWTError as exc:
            # The library's message names the failure mode; the client gets a
            # code and nothing else.
            if "expired" in str(exc).lower():
                raise AuthenticationError(error_codes.TOKEN_EXPIRED) from exc
            raise AuthenticationError(error_codes.TOKEN_INVALID) from exc

    def new_refresh_token(self) -> tuple[str, str]:
        plaintext = secrets.token_urlsafe(48)
        return plaintext, self.hash_refresh_token(plaintext)

    def hash_refresh_token(self, plaintext: str) -> str:
        """Keyed hash, so a leaked database alone does not yield usable tokens."""
        return hmac.new(
            self._secret.encode(), plaintext.encode(), hashlib.sha256
        ).hexdigest()
