# ADR 0009 — What the audit found, and what was fixed first

## Status
Accepted, 29 August 2026. Partially applied — the remaining items are listed.

## Context
"Make the app complete" is not a task until you know what is missing. A
six-way read-only sweep of the codebase produced about 140 findings; after
deduplication and re-reading the cited code, 34 survived.

The finding that reframes the rest: **the negotiated-fare path is the only
journey the product actually implements**, and it broke at four points.

Two sweeps were partly stale — they read the tree while the جواز سیر move was
half-applied and reported its intermediate state as defects. Their claims were
checked against the current tree and dropped. That is worth recording: a sweep
of a moving repository reports the movement.

## Fixed here

**A cancelled trip left the passenger holding a boarding code.**
`TRIP_TO_BOOKING_STATUS` mapped four of the twelve trip states, and
`cascade_bookings` returns 0 for anything absent from it. So a driver
cancelling a trip left every booking at `DRIVER_ASSIGNED` or `READY` — with the
app still rendering the boarding code under "Coming up", for a vehicle nobody
was driving. The three ways a trip ends without travelling now cancel the
bookings riding on it.

`ONBOARD` is deliberately not caught: `BOOKING` has no `ONBOARD → CANCELLED`
edge, so `follow_trip` leaves those alone. Once someone is in the vehicle the
journey happened, whatever later becomes of the trip record — and cancelling
their booking would erase a ride that was taken, along with the fare the driver
is owed.

**And nobody told them.** The cascade was silent. The passengers are now read
*before* the cascade rather than after — cancelling their bookings takes them
out of `active_for_trip`, so a list gathered afterwards is empty. That is the
second time this exact mistake has been made in this codebase; the first was the
losing-driver notification.

**The driver never learned their bid was accepted.** The server writes
`notify.offer.accepted` to an inbox with four endpoints, and mobile had no
client for any of them — no Retrofit paths, no repository, no FCM. Meanwhile
`DriverHomeViewModel` called `refresh()` once in `init`, and the ViewModel is
retained on the back stack, so returning from the board did not re-run it. A
passenger stood at a station waiting for a driver who did not know they had won.

There is still no push transport (no Firebase credentials, and none mine to
create), but ADR 0005 already made the inbox row the record and delivery an
optimisation on top. So: a notification client, a poll on the driver's home
screen, and the unread messages rendered where the driver is looking. Polling
only while there is something to learn — an offline driver with no trip is not
spending a data bundle to hear nothing.

**An expired request left the passenger on a permanent spinner.**
`OffersScreen` branched on `liveOffers.isEmpty()` and never read the status. The
server closes a stale request on that very read, so past the TTL the reply is
`EXPIRED` with no offers — spinner over "waiting for drivers", forever, while
the view model stops polling because the request is closed. It now reads the
status and offers a way back to asking.

**A failed earnings call removed every control on the driver's home screen.**
`Earnings()` opened with `state.earnings ?: return`, which took the section's
only navigation button with it. An approved, offline driver whose earnings call
failed was left with one control — the online switch — and nothing explaining
it.

**A driver could not cancel an assigned trip.** The API accepted `CANCELLED`
and the schema whitelisted it; the app's `nextStep` only ever walked forward, so
a driver whose car broke down at a pickup point had exactly two options — drive
the trip, or abandon the passenger silently. There is now a cancel control, and
it asks *why*: a cancellation with no recorded reason cannot be told from any
other, and the one that costs a passenger a morning is the one a suspension has
to be able to point at. The reason codes offered are the ones the server
accepts, so the app cannot present a choice that fails. No fee is charged — the
passenger did not cancel; the ride was taken from them.

**Nothing called `/admin/routes/generate`.** The endpoint's own docstring says
"Needed after a village import", and no admin page called it. So every village
imported so far produced stations with no routes — and a station with no route
is not on the network, whatever the map says: it cannot be chosen as an origin
and nothing can be booked from it. It is now offered on the import page at the
moment it is needed, and as a standing action on the routes page.

## Not fixed here, in the order they should be
1. No support, help or emergency surface anywhere — the tables, the error codes
   and the translated strings all exist.
2. No screen in either app has a title bar or back affordance; `BackHandler`
   appears nowhere.
3. The fixed-price search path is still reachable by pressing Back from the ask
   step, contradicting the negotiated-fare model.
4. A driver cannot view a document photo they uploaded, though the reviewer can.
5. `Locale.displayName()` returns bare "دری" / "پښتو" literals into a Compose
   file, against the house rule the same module's header asserts.

## Verified
Reverting the cascade fails two tests in Python and one in Kotlin — the shared
specification catches the mirror going stale, which is what it is for. The
notification test fails without the notifier wired into the advance endpoint.
Both new e2e tests were watched failing before the fix existed.
