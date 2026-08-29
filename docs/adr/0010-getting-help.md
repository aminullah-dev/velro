# ADR 0010 — VELRO is not an emergency service, and says so

## Status
Accepted, 29 August 2026. First slice shipped.

## Context
A driver alone on a mountain road at night, or a passenger whose driver never
arrived, had no path anywhere in the product. The tables, the enums, the error
codes, the `require_support` dependency, the `TKT` number format and four
translated `trip.emergency.*` keys all existed and were wired to nothing.

Three independent designs were written from different framings — worst moment
backwards, network backwards, operator backwards — and each was judged through
three lenses: does it promise what VELRO cannot deliver, does it work in a
valley, could it be built here. Two tied at 25/30 and agreed on the essential
point.

## Decision

**The promise comes first, and the code follows from it.** VELRO has no 24/7
call centre, no emergency-services integration and no push transport. A button
that implies rescue and delivers a database row is worse than no button. So the
first line on the screen, above every control, is:

> ولرو خدمات عاجل نیست. ما کسی را نزد شما فرستاده نمی‌توانیم.
> *VELRO is not an emergency service. We cannot send anyone to you.*

**Three doors, in the order a person in trouble needs them.**

1. **Dial 119 or 100.** Zero bytes, no permission, works on a handset that has
   never reached VELRO. First, because it is the only one that brings anybody.
2. **Send the car's details to someone who will actually come.** The message is
   pre-written; the recipient is chosen in the person's own SMS app. No contact
   list leaves the handset, and VELRO never holds a table of which women in
   Ghorband have which male relatives — a hazard it would gain nothing by
   carrying, given it cannot send SMS anyway.
3. **Tell VELRO.** Needs data, and the button says out loud that nobody may
   read it until morning.

**The numbers are compiled into the app.** `SafetyContacts.BUILT_IN`. The
server copy is better — an operator can change it without a release — but the
moment these are needed is the moment the network is least likely to be there.
`GET /support/contacts` exists so the numbers can be changed, not so the phone
can find them in an emergency; by then it is too late to ask. It is the one
unauthenticated endpoint in VELRO, because a passenger whose session expired in
a valley must still be able to see 119.

**A placeholder number is never offered.** `support.contact_phone` ships as
`+93700000000`. Rendering a "call VELRO" row against it would put a dead control
on the screen at the moment somebody is frightened; they would press it and
wait.

**`ACTION_DIAL`, never `ACTION_CALL`.** No `CALL_PHONE` permission, so no
permission dialog at the worst possible moment, and the app never places a call
somebody did not see.

**The queue orders itself.** Urgent categories first, then oldest. Nobody is
watching overnight, so the ordering *is* the triage — a safety report raised at
02:00 must not be pushed down the page by a fare dispute raised at 09:00 with no
human awake to notice it happening.

**Internal notes never reach the reporter.** Operators need somewhere to write
"this driver has three of these", and it must not be the thread the driver is
reading.

**A reply from the person who raised it reopens a resolved report.** Marking
something fixed is a claim; they are the one who knows.

## Deliberately not built
- **No SOS that alerts VELRO as its primary action.** With no push transport
  that reaches an operator when they next open a browser. In a snowstorm on a
  valley road, nobody.
- **No trusted contact stored server-side.** No column, no endpoint.
- **No passenger location tracking.** A background trail on a woman is
  something VELRO would then hold and could be compelled to hand over.
- **No SMS VELRO pays for.** Nobody has approved that spend.
- **No automatic driver suspension.** A human reads it and a human decides.

## What the manifest fix bought
Neither app had a `<queries>` block. On `targetSdk 35` that makes
`resolveActivity()` return null for `tel:` and `smsto:` even when a dialler
exists — so all three doors would have looked present and done nothing. Verified
on the emulator: the tap now launches
`act=android.intent.action.DIAL cmp=com.google.android.dialer`.

## Verified
Fourteen backend tests. Breaking each guarantee in turn — offering the
placeholder number, leaking internal notes, ranking the queue by time instead of
danger — fails its test. A guard reads the Kotlin `BUILT_IN` categories and
asserts they equal the domain's, because a category the app offers and the
server rejects is a report form that fails on submit for somebody who has just
described being in danger.

## Still to build
The passenger's report form and the operator's queue page in the admin panel.
The backend and the sheet are done; the report button is wired to nothing on the
passenger side yet, which is why it is not rendered rather than rendered dead.
