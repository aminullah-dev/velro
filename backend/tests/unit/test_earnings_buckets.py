"""How a driver's week is cut into buckets.

The chart on the earnings screen is only as honest as this. Three ways it can
be wrong without anything failing:

    a week that starts on Monday    splits the Afghan weekend across two bars
    a month that rolls back wrong   loses December, or repeats it
    a window that skips a period    draws a quiet day as no day at all

None of those raise. They just draw a picture the driver believes.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ui.api.routers.settlements import _bucket_for, _bucket_starts


class TestDays:
    def test_returns_the_asked_for_count_oldest_first(self):
        starts = _bucket_starts("DAY", 7)
        assert len(starts) == 7
        assert starts == sorted(starts)

    def test_buckets_are_exactly_one_day_apart(self):
        starts = _bucket_starts("DAY", 5)
        gaps = {starts[i + 1] - starts[i] for i in range(len(starts) - 1)}
        assert gaps == {timedelta(days=1)}

    def test_the_last_bucket_is_today(self):
        now = datetime.now(UTC)
        assert _bucket_starts("DAY", 3)[-1].date() == now.date()

    def test_every_bucket_starts_at_midnight(self):
        for start in _bucket_starts("DAY", 4):
            assert (start.hour, start.minute, start.second) == (0, 0, 0)


class TestWeeks:
    """The Afghan week runs Saturday to Friday."""

    def test_every_bucket_begins_on_a_saturday(self):
        # Python: Monday is 0, so Saturday is 5.
        assert {s.weekday() for s in _bucket_starts("WEEK", 8)} == {5}

    def test_buckets_are_exactly_one_week_apart(self):
        starts = _bucket_starts("WEEK", 6)
        gaps = {starts[i + 1] - starts[i] for i in range(len(starts) - 1)}
        assert gaps == {timedelta(weeks=1)}

    def test_the_current_week_is_included(self):
        now = datetime.now(UTC)
        assert _bucket_starts("WEEK", 4)[-1] <= now


class TestMonths:
    def test_every_bucket_is_the_first_of_a_month(self):
        assert {s.day for s in _bucket_starts("MONTH", 12)} == {1}

    def test_walking_back_a_year_crosses_the_new_year_exactly_once(self):
        starts = _bucket_starts("MONTH", 12)
        assert len(starts) == 12
        # Consecutive months, no repeats and no gaps.
        as_pairs = [(s.year, s.month) for s in starts]
        assert len(set(as_pairs)) == 12
        for (y1, m1), (y2, m2) in zip(as_pairs, as_pairs[1:]):
            expected = (y1 + 1, 1) if m1 == 12 else (y1, m1 + 1)
            assert (y2, m2) == expected

    def test_thirteen_months_reaches_the_same_month_last_year(self):
        starts = _bucket_starts("MONTH", 13)
        first, last = starts[0], starts[-1]
        assert first.month == last.month
        assert first.year == last.year - 1


class TestAssignment:
    def test_an_entry_lands_in_the_bucket_it_falls_within(self):
        starts = _bucket_starts("DAY", 5)
        # Midday of the third bucket.
        when = starts[2] + timedelta(hours=12)
        assert _bucket_for(when, "DAY", starts) == starts[2]

    def test_an_entry_exactly_on_a_boundary_belongs_to_the_newer_bucket(self):
        starts = _bucket_starts("DAY", 5)
        assert _bucket_for(starts[3], "DAY", starts) == starts[3]

    def test_an_entry_older_than_the_window_is_dropped_rather_than_folded_in(self):
        # Folding it into the oldest bucket would silently inflate one bar
        # with every trip the driver ever made.
        starts = _bucket_starts("DAY", 5)
        ancient = starts[0] - timedelta(days=400)
        assert _bucket_for(ancient, "DAY", starts) is None

    def test_a_future_entry_lands_in_the_newest_bucket(self):
        starts = _bucket_starts("DAY", 5)
        assert _bucket_for(starts[-1] + timedelta(hours=6), "DAY", starts) == starts[-1]


class TestBucketise:
    """The fold from commission rows, which is where the cash bug lived.

    The summary used to read the wallet ledger, where a completed booking
    writes exactly one entry -- COMMISSION for a cash fare, TRIP_EARNING
    otherwise -- so an all-cash driver showed zero journeys and a negative
    net. These pin the new source: one commission row is one journey, and the
    three figures come from the row rather than being derived.
    """

    @staticmethod
    def _row(when, gross=90_000, platform=9_000):
        from types import SimpleNamespace
        return SimpleNamespace(
            created_at=when, gross_minor=gross,
            platform_minor=platform, driver_minor=gross - platform,
        )

    def test_a_cash_journey_is_still_a_journey(self):
        from ui.api.routers.settlements import _bucket_starts, _bucketise
        starts = _bucket_starts("DAY", 3)
        rows = [self._row(starts[-1] + timedelta(hours=2))]
        earned, commission, net, trips = _bucketise(rows, "DAY", starts)
        assert trips[starts[-1]] == 1
        assert earned[starts[-1]] == 90_000
        assert commission[starts[-1]] == 9_000
        assert net[starts[-1]] == 81_000

    def test_net_is_the_recorded_driver_share_not_a_subtraction_here(self):
        from ui.api.routers.settlements import _bucket_starts, _bucketise
        starts = _bucket_starts("DAY", 2)
        # A row whose split does not sum (cannot happen upstream; the point is
        # that the fold reports what was recorded rather than recomputing).
        from types import SimpleNamespace
        row = SimpleNamespace(
            created_at=starts[-1], gross_minor=100,
            platform_minor=10, driver_minor=89,
        )
        *_, net, _t = _bucketise([row], "DAY", starts)
        assert net[starts[-1]] == 89

    def test_rows_before_the_window_are_dropped_not_folded_in(self):
        from ui.api.routers.settlements import _bucket_starts, _bucketise
        starts = _bucket_starts("DAY", 3)
        rows = [self._row(starts[0] - timedelta(days=30))]
        earned, *_ , trips = _bucketise(rows, "DAY", starts)
        assert sum(earned.values()) == 0
        assert sum(trips.values()) == 0
