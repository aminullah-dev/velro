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
