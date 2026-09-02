# ADR 0012 — A contended row is held before it is decided on

## Status
Accepted, 2 September 2026.

## Context
The audit that produced this record found five places where two requests
arriving in the same instant both passed a check that was true when each of
them read it and false by the time either committed:

- two drivers accepting one scheduled trip (`AcceptTrip` read the trip with
  `get`; its docstring said it was locked);
- one driver accepting two trips at once (nothing held the driver row);
- two passengers accepting two of one driver's bids (`AcceptOffer` held only
  its own request row);
- a payout marked paid twice (`DecideSettlement` read the settlement and the
  wallet unlocked, and drained the hold twice);
- a booking cancelled twice (`CancelBooking` read the booking unlocked, and
  wrote two cancellation records).

Every one of them was invisible to a sequential test and to a code read: the
guard was present, and it was simply not a guard. Each reproduced on the first
run of a two-thread test against a real PostgreSQL with the result
`['WON', 'WON']`.

The seat race, by contrast, had been right from the start: the trip row and
the seats are held `FOR UPDATE`, and a unique constraint stands behind them.
The rule existed; it had been applied to the one path everyone knew was
contended and to none of the others.

## Decision
**A use case that decides something about a row holds that row `FOR UPDATE`
before it reads the state it decides on.** `SqlRepository.lock` is how; it
exists on every repository. A status check on a row obtained through `get` or
`find` is a check about the past and must not gate a write.

**Locks are taken in one order everywhere: trip, then driver; request, then
driver.** `AdvanceTrip` holds the trip and then writes the driver's
availability; `AcceptTrip` now holds the trip and then the driver; `AcceptOffer`
holds the request and then the driver. Nothing holds a driver and then wants a
trip or a request, so no two of these can wait on each other in a cycle.

**Money moves only on a held row.** A settlement is held before its status is
advanced; the wallet it drains is held before the drain. The seat, booking and
number-sequence paths already worked this way.

**Every such guarantee has a race test.** `tests/integration/test_seat_concurrency.py`,
`test_driver_assignment_concurrency.py` and `test_money_concurrency.py` each
run two real transactions through one barrier and assert exactly one winner
and the state the loser left behind. A new contended writer is not done until
its test has been watched failing on the unlocked code.

**A mutation the handset can retry carries an idempotency key.** Booking,
accept and -- as of this record -- the passenger's ask. The key collapses a
retry into the original; the lock refuses a genuine second attempt. They are
different guarantees and both are needed.

## Consequences
- The second of two simultaneous callers now waits for the first, which on
  these tables is milliseconds. Nothing serialises across trips or drivers,
  only within one.
- A reader must not take a lock: reads through `get`/`find` stay cheap and
  concurrent. The rule is about writers.
- A future contended writer that forgets the lock will pass every sequential
  test. The integration suite is the only thing that catches it, which is why
  `scripts/check.sh` runs it on every push and why it needs a real PostgreSQL.
