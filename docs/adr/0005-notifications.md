# ADR 0005 — The inbox is the record, the push is a convenience

## Status
Accepted, 29 August 2026.

## Context
The negotiated model only works if people learn things happened. A driver will
not sit watching the board, and a passenger will not hold the offers screen open
in a valley. Both need to be told.

A `NotificationChannel` port and a `RecordingNotifier` already existed and were
wired to nothing — a notification layer that notified nobody.

Firebase credentials are not in this repository and are not mine to create, so
push cannot actually be sent yet.

## Decision
**Every notification is written to the database first, then delivery is
attempted.** The row is the product; delivery is an optimisation on top of it.

That ordering is not a compromise forced by the missing credentials. It is what
the network in Ghorband requires. A push that does not arrive must leave a
message waiting in the app, and an operator must be able to see that it failed
rather than wonder.

**Delivery can never fail the thing it is reporting.** Every call goes through a
helper that swallows exceptions, because if telling someone their fare was
accepted can undo the acceptance, then a bad afternoon on the network becomes an
afternoon with no rides.

**Push targets registered devices, and registering upserts on the token.**
Handsets in this market are shared and reinstalled. A token appearing under a
second person moves rather than duplicating, or a driver's ride offer goes to
whoever had the phone last. A token the push service rejects is deleted, not
soft-deleted: a dead address is not history, and keeping it means retrying it
for ever.

## What is notified
- A driver named a price → the passenger
- A passenger accepted → that driver, with the booking number
- A passenger accepted → **every other driver who offered**

The third is the one nobody asks for and everybody needs. Losing quietly costs a
driver a journey across a valley to a station where the passenger has already
gone.

## Consequences
No transport is configured, so `delivery_status` is `FAILED` on every row today
and the tests assert exactly that — the layer is honest about having delivered
nothing rather than claiming success. Adding Firebase is a transport passed to
`build_notifier`, not an edit at any call site.

SMS is the intended second channel and is not built. It costs money per message,
so it should be a deliberate fallback for a few events rather than a mirror of
everything, and that choice belongs to whoever is paying.

Writing the test for the losing drivers found that notification had never
worked: the offer rows were read before declining them, but the UPDATE expires
those objects, so re-reading `status` afterwards found `DECLINED` and matched
nobody. Ids are now captured before the update. It would have shipped silent.
