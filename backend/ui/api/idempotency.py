"""Idempotent mutations.

Offline clients retry. On the connections this product targets, a request that
timed out at the handset very often succeeded at the server, so every mutation
must assume it will arrive more than once.

The rule: same key and same body returns the stored response; same key and a
different body is a client bug and returns 409. A key is scoped to an endpoint
so two different operations cannot collide on one.
"""

from __future__ import annotations

import functools
import hashlib
import json
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from sqlalchemy.exc import IntegrityError

from shared import error_codes
from shared.errors import ConflictError


def body_hash(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def idempotent(endpoint: str) -> Callable:
    """Decorator applied to a router function.

    Deliberately a no-op when the client sends no key: making the header
    mandatory would break a first-time caller, and the guarantee is only
    meaningful to a client that wants it.
    """

    def decorate(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = kwargs.get("idempotency_key")
            store = _find_store(kwargs)
            if not key or store is None:
                return func(*args, **kwargs)

            body = kwargs.get("body")
            digest = body_hash(body.model_dump() if hasattr(body, "model_dump") else body)

            existing = store.find(key, endpoint)
            if existing is not None:
                if existing.request_hash != digest:
                    raise ConflictError(
                        error_codes.IDEMPOTENCY_KEY_REUSED, key=key, endpoint=endpoint
                    )
                return existing.response_body

            result = func(*args, **kwargs)

            from shared.clock import SystemClock
            from shared.ids import new_id

            # Round-tripped through JSON: the column is JSON, and a Pydantic
            # ``model_dump()`` leaves datetimes as objects the driver cannot
            # adapt. Storing them raw fails at commit, long after the handler
            # has returned.
            storable = json.loads(json.dumps(result, default=str))

            store.remember(
                id=new_id(),
                key=key,
                endpoint=endpoint,
                request_hash=digest,
                response_status=200,
                response_body=storable,
                expires_at=SystemClock().now() + timedelta(hours=24),
            )
            try:
                # Flushed here rather than left to the request-end commit. Two
                # retries of one key can both miss the store and both run the
                # handler -- the handset's transport retry racing the person's
                # own tap is the ordinary way, not the exotic one. The unique
                # constraint kills the second INSERT either way; flushing pulls
                # that violation forward to where it can be handled, instead of
                # letting it surface after this wrapper has returned, as a 500
                # on a request whose work the winner had already done.
                store.session.flush()
            except IntegrityError:
                # The loser's whole transaction goes -- including its duplicate
                # handler work, which is exactly the discard we want -- and the
                # caller gets the winner's stored answer, as if the retry had
                # simply arrived a moment later.
                store.session.rollback()
                winner = store.find(key, endpoint)
                if winner is not None and winner.request_hash == digest:
                    return winner.response_body
                raise
            return result

        return wrapper

    return decorate


def _find_store(kwargs: dict[str, Any]) -> Any | None:
    from infrastructure.db.repositories.ops import IdempotencyRepository

    for value in kwargs.values():
        if isinstance(value, IdempotencyRepository):
            return value
    return None
