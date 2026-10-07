# ADR 0015 — Passengers name the place they stand in, and the name is kept without them

## Status
Accepted, 21 September 2026.

## Context
A passenger chooses an origin by district, then village, then station. That
works for someone who knows the list. It does not work for someone standing
at the roadside who wants to say "here", and it does not teach VELRO anything:
only 49 of the 427 villages in the master file have a point on the map, and
Surkh Parsa has none.

The phone already knows where the passenger is. It can find the nearest
station, and from that the district. What it cannot know is what people call
the spot. The passenger can tell us, and the next passenger standing there
should not have to.

Two things pull against each other. A name that is kept and offered to
strangers is public. "خانه" at a precise coordinate is one family's front
door, and "خانهٔ کاکا" is that plus a relationship. On the other hand, a filter
strict enough to refuse every such name must never refuse a real village. A
passenger told that their village "is not a place" learns that VELRO does not
know where they live.

## Decision
**The origin is still a station.** `ride_requests.origin_station_id` stays
NOT NULL. "Current location" resolves to the nearest station
(`GET /geo/resolve`), and that is where the passenger boards. The named place
is an optional `origin_place_id` beside it. On the driver's board it appears
as the line under the station: "from قلعه نو".

**The district is inferred, never typed.** The nearest placed station decides
the district (`district_source: "station"`). A district centre is the
fallback (`"centre"`), and it is the seed's guess. The app shows the result
with a way to change it. `POST /geo/places` accepts the corrected
`district_id`.

**Only public place names.** `domain.places` refuses the following before
anything is stored:
- household, trade and family words in Dari, Pashto and English, with their
  suffixes (خانه، منزل، کور، دکان، کاکا، زما، my…);
- digits, which cover phone numbers and house numbers;
- contact details;
- a bare kind of place such as "مسجد" or "دلته";
- anything longer than a name (more than 5 words or 60 characters).

Every name in `resources/geo/geography.csv`, 854 in all, is tested to pass,
so the filter cannot grow teeth unnoticed. The reason travels with
`PLACE_NAME_NOT_ALLOWED`, so the app can say what to write instead.

**Automatic where certain, a person where not.**
- A name that matches a known village or alias in that district is `APPROVED`
  at once. The match is exact up to spelling (ZWNJ, spaces, قریه/ده/کلی), and
  the name must be typed within 6 km of the village's point, if it has one.
- Anything else is `PENDING`. A PENDING name is shown to nobody but the
  drivers deciding about the one request it came with. That is no more than
  the free-text note already shows them.
- Staff approve (optionally with a corrected spelling, which goes through the
  same filter) or reject at `/admin/places`. A rejected name stays rejected:
  typing it again at the same spot is refused with reason `rejected`, not
  queued again.

**One row per place, not per report.** The same name (`place_key`: spelling-
and space-insensitive) in the same district within 1.5 km increments
`report_count`. Staff read the queue most-reported first.

**Anonymous by construction.**
- `places` has no user column, and `created_by` is never written.
- The passenger's report writes no audit entry. Staff decisions are audited
  with the staff member's id.
- `/geo/resolve` writes nothing, and the request log records paths, not query
  strings.
- The link between a passenger and a place exists only on their own ride
  request, exactly as the link to their origin station always has.
- A PENDING place comes back only in the POST response, so the app keeps it
  in the passenger's own recents on the phone.

**Fenced and signed in.** Naming a place requires a signed-in account and the
same geofence as asking for a ride, including the mock-location refusal. A
fix whose reported accuracy is worse than 300 m is refused
(`PLACE_FIX_TOO_COARSE`), because coarse location cannot tell three villages
apart.

## Consequences
- The privacy page changes in the same commit. It now says passengers'
  location also shows the nearest station, and that a named place is kept
  without them.
- The apps must ask for precise location, not only approximate, to offer
  naming. Approximate location still resolves a station.
- `places` rows never carry a person. Account deletion (ADR 0014) therefore
  has nothing to erase there. It does clear `origin_place_id` on the deleted
  passenger's requests, along with the notes. That link is the one thing
  that ties her to a place.
- An approved place near an unplaced village is evidence of where that village
  is. Staff can apply it through the existing village placer. Nothing here
  moves a village's point on its own.
