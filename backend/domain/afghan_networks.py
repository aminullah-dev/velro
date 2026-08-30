"""Which network an Afghan mobile number was issued on.

Needed for two things, both about delivery rather than about VELRO: routing a
message down a route that will actually carry it, and recording per-network
outcomes so a failing operator is visible as a network rather than as a vague
drop in sign-ins.

What is deliberately NOT here: any provider's rules about senders. That AWCC
refuses an alphanumeric sender is a fact about a route, not about Afghanistan,
and a second provider may route differently. It lives with the adapter that
knows it.
"""

from __future__ import annotations

from enum import StrEnum

COUNTRY_CODE = "93"


class Network(StrEnum):
    AWCC = "AWCC"
    ROSHAN = "ROSHAN"
    ETISALAT = "ETISALAT"
    MTN = "MTN"
    SALAAM = "SALAAM"


# The national allocation. Numbers are 07X locally and +937X in E.164, so the
# digit after the 7 is what distinguishes them.
_BY_PREFIX: dict[str, Network] = {
    "70": Network.AWCC,
    "71": Network.AWCC,
    "72": Network.ROSHAN,
    "79": Network.ROSHAN,
    "73": Network.ETISALAT,
    "78": Network.ETISALAT,
    "76": Network.MTN,
    "77": Network.MTN,
    "74": Network.SALAAM,
    "75": Network.SALAAM,
}


def likely_network(e164: str) -> Network | None:
    """The network a number was issued on, or None when it is not Afghan mobile.

    "Likely" is not hedging. A prefix records the original allocation, and
    Afghanistan permits portability, so a 070 number may sit on Roshan today.
    Nothing here can know that -- only a delivery attempt can.

    So this is used to *order* attempts and to label results, never to decide
    that a message cannot be sent. A caller that treats the answer as certain
    will silently fail to reach whoever has moved networks, and will have no
    way of finding out.
    """
    digits = e164.lstrip("+")
    if not digits.startswith(COUNTRY_CODE):
        return None
    national = digits[len(COUNTRY_CODE) :]
    # 9 digits, starting 7. Anything else is a landline, a short code, or noise.
    if len(national) != 9 or not national.startswith("7") or not national.isdigit():
        return None
    return _BY_PREFIX.get(national[:2])
