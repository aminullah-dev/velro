# ADR 0013 — A stored answer opens only for the account that earned it

## Status
Accepted, 2 September 2026.

## Context
Every mutation a handset can retry carries an idempotency key (ADR 0012), and
the passenger's accept of a driver's offer -- the tap that creates the trip,
the booking and the boarding code -- did not. The first attempt to give it
one built the key from the offer id and was reverted the same day, before it
was committed, because it opened a hole:

- the driver holds the offer id: it is the id of his own bid;
- the store was keyed by `(key, endpoint)` alone, with no notion of *whose*
  key it was;
- the decorator returned the stored answer *before* the handler ran, so the
  use case's ownership check -- the only thing standing between a driver and
  a passenger's booking -- never executed on a replay.

A driver could therefore present the passenger's key and read back the
passenger's boarding code: the secret that exists so the driver cannot know
it in advance.

The table had a `user_id` column from the start. Nothing wrote it and nothing
read it.

## Decision
**The user is the boundary, not the key.** An idempotency record is
identified by `(user_id, key, endpoint)`; the unique constraint says so, and
the lookup always filters by the authenticated actor. A route with a key but
no actor to scope it to gets no idempotency at all rather than unscoped
idempotency. The only answer a caller can ever have replayed is one the same
account already received, so a replay can never be a way around a handler's
own authorization.

**A request's identity is the body and every plain path or query value.**
An accept has no body and names its offer in the path. The same account
sending the same key for a different offer, a different trip or a different
body is refused with `IDEMPOTENCY_KEY_REUSED`, never answered with the
earlier request's result.

**Only a success is remembered.** A refusal -- permission, conflict, not
found -- consumes nothing, so the same tap after the cause has cleared goes
through. This was already the rule; it is now written down.

**A twin that lost the row lock is handed the winner's answer.** The same
account's transport retry can arrive while its own first attempt is still
inside the lock. The loser waits, finds the state the winner made, and raises
a conflict. Before that conflict is returned, the store is checked once more
under this user alone; a committed record with the same key and the same
request identity is the winner's answer, and it is returned instead. Nothing
the loser did is kept -- its transaction is rolled back first. This does not
replace the lock: the lock still decides who builds the journey, and it is
still the only thing that stops two of them.

**The client's key is private to the client.** The handset builds the accept
key from the offer id *and* an attempt id it holds for the visit to the
screen, as the ask and the booking already do. The server does not depend on
this -- the scope above is the guarantee -- but a key nobody else can name is
one nobody else will try.

## Consequences
- `tests/e2e/test_accept_offer_idempotency.py` holds the contract: the same
  passenger replays sequentially and under a two-thread race; a second
  passenger, the offering driver and a stranger driver each get `403` and no
  code, including with the reverted design's offer-id-only key; the same key
  on a different offer, a different body or a different endpoint never
  replays; a refused accept does not spend the key; and the code is read on
  the passenger's booking and nowhere on the driver's side.
- Records written before this change (no user) match nobody and expire within
  a day. A retry that straddles the deploy is refused once with
  `IDEMPOTENCY_KEY_REUSED` and succeeds with a fresh key.
- `driver.accept` gains the same path-parameter binding it was missing: one
  key can no longer be carried from one trip to another.
