# ADR 0004 — The fare is negotiated, not calculated

## Status
Accepted, 29 August 2026. Supersedes the fixed-fare assumption in ADR 0001.

## Context
VELRO priced a journey from a `fare_rules` table: a route, a ride kind, an
amount. That worked for ten seeded villages and collapsed at 425.

It collapsed because the platform does not have the information. Nobody knows
how many kilometres separate two villages in Ghorband, which stretch of the road
is asphalt and which is dirt that turns to mud in spring, or which pass is shut
after snow. Pricing 2,905 generated routes would have meant inventing 2,905
numbers, and a wrong fare is not a cosmetic error: it is a driver refusing at
the roadside, or a passenger overcharged.

The people who do know are the driver and the passenger, and they already settle
it between them at the station.

## Decision
The fare is agreed, not computed.

1. A passenger asks for a ride at a price they name.
2. Drivers answer with a price. A driver happy with the asking price offers
   exactly that number -- there is no separate "accept", so one path carries
   both answers and the passenger's list reads the same either way.
3. The passenger picks one. That creates the trip, the seats and the booking,
   and the agreed amount is frozen onto the booking as it always was.

No endpoint suggests a fare, because there is no fare to suggest.

## What is still enforced
Not pricing does not mean not caring.

- **Implausible prices are refused.** More than five times or less than a fifth
  of what was asked is almost always a missing zero or one too many. Refusing
  costs a retype; accepting costs an argument at the roadside.
- **No self-bidding.** One person offering on their own request would
  manufacture a completed trip, and with it a commission record and a rating.
- **One live offer per driver per request**, as a partial unique index.
  Changing your mind is withdrawing and offering again, so the passenger sees
  one number per driver rather than a negotiation to read through.
- **One open request per passenger.** Three live requests take three drivers off
  the board for one journey.
- **Accepting closes the rest.** Every other driver is told at once rather than
  keeping an offer that can never be accepted and finding out by driving to a
  station where nobody is waiting.

Seats go through `lock_available` and `reserve`, exactly as a scheduled booking
does. There is no contention on a trip created a line earlier, but two ways of
taking a seat would be two places for the guarantee to weaken, and that
guarantee is the one the product rests on.

## Consequences
`fare_rules` is not deleted. Scheduled shared trips still have a published
price, which is how a minibus leaving at 07:00 works, and a booking made under
the old model must still explain its own receipt. What is gone is the assumption
that every journey has one.

`FareQuote.route_id` is now optional. Two people can agree to make a journey
whether or not VELRO has modelled the route between their villages, and refusing
the booking because the route table is incomplete would be the platform putting
its own bookkeeping ahead of the trip.

A negotiated booking's receipt carries one line, `fare.component.agreed`. A
breakdown would imply a calculation that did not happen.
