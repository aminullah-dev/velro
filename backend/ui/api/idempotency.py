"""Idempotent mutations.

Offline clients retry. On the connections this product targets, a request that
timed out at the handset very often succeeded at the server, so every mutation
must assume it will arrive more than once.

The rule: the same user sending the same key for the same request gets the
stored response; the same user sending the same key for a different request
is a client bug and gets 409. A key is scoped to an endpoint, so two different
operations cannot collide on one -- and to the authenticated user, so nobody
else's key can ever open a stored answer.

The user is the boundary, not the key. The record is looked up under the
authenticated actor before anything else happens, so the only response that
can ever be replayed to a caller is one the same account already received. A
stored answer is never a way around the handler's own ownership checks: a
different account presenting the same key finds nothing, runs the handler, and
is refused by it exactly as if the key had never existed (ADR 0013).

The request's identity covers the body and every plain path or query value,
not the body alone. An accept has no body and names its offer in the path; a
key that replayed the first offer's answer against a second offer would be a
lie the client could not detect.
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

KEY_KWARG = "idempotency_key"


def body_hash(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def request_digest(kwargs: dict[str, Any]) -> str:
    """What this request *is*, for deciding whether a repeat is the same one.

    The body, plus every plain value the route received from the path or the
    query string. Repositories, the actor and the key header itself are how
    the request is served, not what it asks for, and are left out.
    """
    body = kwargs.get("body")
    params = {
        name: value
        for name, value in kwargs.items()
        if name not in ("body", KEY_KWARG)
        and (value is None or isinstance(value, str | int | float | bool))
    }
    return body_hash(
        {
            "body": body.model_dump() if hasattr(body, "model_dump") else body,
            "params": params,
        }
    )


def idempotent(endpoint: str) -> Callable:
    """Decorator applied to a router function.

    Deliberately a no-op when the client sends no key: making the header
    mandatory would break a first-time caller, and the guarantee is only
    meaningful to a client that wants it. Equally a no-op when the route has
    no authenticated actor to scope the record to: an unscoped record is the
    hole this module exists to close, so rather than keep one, the request
    simply runs once and is not remembered.
    """

    def decorate(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = kwargs.get(KEY_KWARG)
            store = _find_store(kwargs)
            actor = _find_actor(kwargs)
            if not key or store is None or actor is None:
                return func(*args, **kwargs)

            user_id = actor.user_id
            digest = request_digest(kwargs)

            existing = store.find(key, endpoint, user_id=user_id)
            if existing is not None:
                if existing.request_hash != digest:
                    raise ConflictError(
                        error_codes.IDEMPOTENCY_KEY_REUSED, key=key, endpoint=endpoint
                    )
                return existing.response_body

            try:
                result = func(*args, **kwargs)
            except ConflictError:
                # The handler refused because of the state it found -- and one
                # way to find that state is to have waited on a row lock while
                # a twin of this very request, same account and same key, made
                # it. That is the retry the store exists for, arriving before
                # the first answer had left. Nothing this attempt did is kept:
                # the transaction goes, then the twin's committed answer is
                # looked for under this user alone. Any other refusal stands.
                store.session.rollback()
                twin = store.find(key, endpoint, user_id=user_id)
                if twin is not None and twin.request_hash == digest:
                    return twin.response_body
                raise

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
                user_id=user_id,
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
                # simply arrived a moment later. The constraint is per user, so
                # the winner is necessarily this same account's twin.
                store.session.rollback()
                winner = store.find(key, endpoint, user_id=user_id)
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


def _find_actor(kwargs: dict[str, Any]) -> Any | None:
    from ui.api.deps import Actor

    for value in kwargs.values():
        if isinstance(value, Actor):
            return value
    return None
