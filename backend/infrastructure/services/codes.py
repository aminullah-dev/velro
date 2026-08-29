"""Code generation: OTPs and booking verification codes.

Both use ``secrets``. A predictable booking code lets a stranger board someone
else's seat, and a predictable OTP is an account takeover.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from domain.identity import PhoneNumber

# No I, O, 0 or 1: these are read aloud at a roadside and mistyped constantly.
_UNAMBIGUOUS = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


class SecretsOtpGenerator:
    """Numeric so it can be typed on any keypad and read over a bad phone line."""

    def __init__(self, pepper: str) -> None:
        self._pepper = pepper

    def generate(self, length: int) -> str:
        return "".join(secrets.choice("0123456789") for _ in range(length))

    def hash(self, code: str, phone: PhoneNumber) -> str:
        """Salted with the phone number, so one stolen hash is not a rainbow table.

        The plaintext OTP is never stored and never logged.
        """
        message = f"{phone.value}:{code}".encode()
        return hmac.new(self._pepper.encode(), message, hashlib.sha256).hexdigest()


class SecretsVerificationCodeGenerator:
    """The short code a driver checks against a passenger's booking."""

    def __init__(self, length: int = 4) -> None:
        self._length = length

    def generate(self) -> str:
        return "".join(secrets.choice(_UNAMBIGUOUS) for _ in range(self._length))
