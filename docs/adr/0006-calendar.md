# ADR 0006 — One calendar, pinned to observed Nowruz dates

## Status
Accepted, 29 August 2026.

## Context
The driver's app showed Hijri Shamsi to Dari and Pashto speakers, because that
is the calendar people in Afghanistan actually keep. The admin panel showed
Gregorian. Same instant, two calendars, no way for either side to know.

The failure mode is a support call: a driver says "I sent the tazkira on
۷ سنبله", the operator searches ۲۹ اگست, and neither of them can work out why the
other is wrong.

Two smaller defects sat underneath it.

**The panel's month names came from the browser.** The formatter read
`locale === "en" ? "en-GB" : "en-GB"` — a ternary whose branches were identical,
so every locale got English month names and the digit localiser then produced
`۲۹ Aug`. Asking Intl for a Persian month name would not have fixed it either:
the CLDR data for Persian gives the Iranian forms (ژانویه, فوریه), and
Afghanistan uses the English-derived ones (جنوری, فبروری).

**The Shamsi leap rule was wrong.** `isShamsiLeap` used the 2820-year (Birashk)
cycle. It makes 1403 a common year and 1404 a leap year; the Nowruz dates
actually observed say the opposite. Every date between 20 March 2025 and
20 March 2026 rendered one day off — 366 days of wrong dates on receipts,
settlements and bookings.

It was not found by reading the code. The arithmetic is correct; the calendar it
describes is not the one Afghanistan keeps. It was not found by the tests
either, because the test listed Nowruz 1404 as 20 March 2025 — written from the
implementation's output rather than from the calendar, so it agreed with the bug
and hid it.

## Decision
**`docs/domain/calendar.json` is the specification, and the observed Nowruz
dates are its only authority.** A leap rule is accepted or rejected by them,
never the other way round. Both implementations — `Calendars.kt` and
`admin/src/i18n/calendar.ts` — are checked against that file, the same way the
two domains are checked against `lifecycles.json`.

**The leap rule is the 33-year cycle**, residues {1, 5, 9, 13, 17, 22, 26, 30}.
It reproduces every observed Nowruz date in the table; the 2820-year rule does
not.

**The fixture includes 1374–1378 on purpose.** The 1398–1405 rows all fall in
one stretch of the cycle and pass under either a correct residue set or one off
by a single number. 1374–1378 are the years that tell them apart — verified by
removing 22 from the set and watching both suites fail.

**Month names are message keys** (`common.month.*`, `common.shamsi_month.*`) in
all three locale files. `Calendars.kt` keeps its own arrays so that formatting a
list needs no dictionary lookup; a test asserts they match the locale files, so
the second copy cannot drift.

**The panel shows Shamsi to Dari and Pashto readers and Gregorian to English
ones** — matching the apps exactly.

## Consequences
The 33-year cycle is an arithmetic approximation of an astronomical calendar and
holds for roughly 1178–1633. A date far outside the fixture's range should be
checked against an almanac before it goes on a printed document; the
specification says so where someone will read it.

`CalendarTest` reads two files at run time that Gradle cannot see, so both are
declared as test inputs. Without that the suite reports its last result forever
— change the specification, watch the tests pass, never learn they were not
re-run. The font test fell into the same trap earlier; this is the second time,
so it is worth stating as a rule: **a test that opens a file must declare it.**

## Verified
- Reverting `isShamsiLeap` to the 2820-year rule fails 4 Kotlin tests.
- Changing one residue (22 → 21) fails 3 Kotlin tests and the Node guard.
- Editing the fixture, or a month name in a locale file, re-runs the suite
  rather than replaying a cached pass.
