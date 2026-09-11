# ADR 0014 — An account deletes itself, and the records it leaves have no name

## Status
Accepted, 11 September 2026.

## Context
The App Store will not list an app that lets somebody open an account and
offers no way to close it from inside the app (guideline 5.1.1(v)); Google's
policy says the same. The privacy page had promised deletion since it went up
-- by writing to us. Nothing in the product could carry it out: an
administrator could suspend an account, never erase one.

Deleting a row was never an option. A passenger's booking is half of a
driver's commission record; a driver's trip is on every passenger's receipt;
ratings are the other person's average. Every read of those goes through a
repository that filters on `deleted_at`, so a soft-deleted user would turn
other people's receipts into 404s.

## Decision
**`DELETE /auth/me` erases the person and keeps the records.** The account
row stays, `DEACTIVATED`, with its phone, name, email and photo emptied.
`users.phone` becomes nullable for exactly this (migration b8e41c2d9f63): the
number is let go, so the same SIM can open a fresh account, and NULL is what
every screen already renders as "no number".

`AccountEraser` (infrastructure/db/repositories/erasure.py) is the one place
that knows which table holds what about a person, with one verb per table:

- **scrub** -- the row stays because other people's records point at it: the
  user, a driver's row (suspended with reason `ACCOUNT_DELETED`), his
  vehicles (retired), notes on requests and bookings, rating comments, names
  and IP addresses in the audit log;
- **delete** -- the row only ever served to reach the person: push tokens,
  sign-in codes, where his car is now; driver and vehicle documents are
  soft-deleted and their photographs unlinked from disk;
- **keep** -- trips, bookings, fares, commission, settlements, and safety
  reports, which may concern someone else's safety.

Open requests are withdrawn and open offers withdrawn or declined, exactly as
if the person had tapped cancel; every refresh token is revoked, and the
access tokens meet the `DEACTIVATED` row in `current_actor`.

Three refusals, each something the person can act on: a seat still booked
(`ACCOUNT_HAS_ACTIVE_BOOKING`), a trip being driven (`ACCOUNT_HAS_ACTIVE_TRIP`),
and a staff account (`ACCOUNT_STAFF_UNDELETABLE`) -- for the same reason an
administrator cannot suspend himself.

The router commits before unlinking files. A file unlinked before its row is
safely forgotten would, on a failed commit, leave a live account pointing at
nothing; the other order leaves at worst an orphaned photograph, logged by
key for an operator to remove.

## Consequences
- Backups taken before a deletion still hold the old data until they age out;
  the privacy page says so.
- A handset that loses the answer and retries meets `USER_SUSPENDED` with
  status `DEACTIVATED`. The Android client reads that as done. Nothing but a
  deletion may ever set `DEACTIVATED`, or that reading becomes wrong.
- Any new column that holds something about a person belongs in
  `AccountEraser` in the same commit.
