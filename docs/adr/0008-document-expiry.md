# ADR 0008 — Approval is a moment; a licence is a period

## Status
Accepted, 29 August 2026.

## Context
All four documents were already required — جواز راننده‌گی, تذکره, عکس روی شما,
جواز سیر موتر — and the driver app already collected all four. The gap was not
in what gets uploaded. It was in what happens afterwards.

`Driver.assert_can_work()`, the single gate every dispatch path goes through,
read `approval_status` and nothing else:

```python
def assert_can_work(self) -> None:
    if self.approval_status is DriverApprovalStatus.SUSPENDED: raise ...
    if not self.is_approved: raise ...
```

`is_valid_on` existed and checked expiry correctly. It had exactly one caller:
`approve()`. So expiry was verified once, at the moment of approval, and never
again. A driver approved in Hamal with a licence expiring in Saratan was still
APPROVED in Jadi — carrying passengers on a permit no longer valid, with
VELRO's word behind them.

The comment in the go-online handler said "Approval covers the documents". It
covered them once.

## Decision
**`assert_documents_current(required, on=)` runs every time a driver goes
online.** Once a shift, so the read is cheap, and it is the last point before a
passenger is involved.

**It fails closed.** If a caller builds the `Driver` aggregate without its
documents, every required code comes back stale and the driver is stopped. The
alternative — an empty list reading as "nothing expired" — turns a forgotten
join into an unlicensed driver carrying passengers, and no test would catch it.
A loud bug is the better failure.

**`DRIVER_DOCUMENTS_EXPIRED` is its own code**, not `DOCUMENTS_INCOMPLETE`.
Nothing is missing; the driver sent everything and was approved. Telling them
their paperwork is absent when a date simply passed sends them looking for the
wrong thing.

**The driver is warned before it happens.** The document row now shows the
expiry — grey when far off, amber within thirty days, red once past — because
the alternative is learning about it when refused at the start of a shift, with
a passenger already waiting and nothing on screen to explain why. Thirty days is
long enough to reach an office in a valley where that is a day's travel.

**The app's boundary matches the server's.** A permit is good *through* its
expiry date (`expires_on >= today`) on both sides. If they disagreed, the app
would tell a driver they are fine and the server would refuse them.

## Consequences
Recovering takes three steps, not one: send a new photo → an operator verifies
it → an operator approves the driver again. The third is not new — replacing any
document already returns a driver to PENDING by design, because the approval was
for the documents that were reviewed. It is worth knowing that the driver is
still blocked after the new licence is verified, and the tests walk that path so
nobody assumes otherwise.

An unparseable expiry date renders no line at all rather than guessing.
Showing a malformed date as "expired" would tell a driver holding a valid
licence to stop working.

## Still open
جواز سیر موتر is modelled as a *driver* document, but it belongs to a vehicle.
A driver with two cars has one جواز سیر slot, so the second car's permit has
nowhere to live and the first one's stands in for both. Moving it to the vehicle
is a schema change and a product decision, so it is not made here.

## Verified
Removing the go-online check fails three e2e tests. The domain rule has four
unit tests, including the fails-closed case and the last-valid-day boundary. The
warning window has five, including the day either side of thirty and the
unparseable date. All were watched failing before the code existed.

On the emulator, one driver with three different expiry states rendered all
three lines correctly, and the home screen named the two documents blocking work.
