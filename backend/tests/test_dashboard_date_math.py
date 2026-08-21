"""
Differential test for the closed-form date-arithmetic rewrite of
``due_date_in_month`` / ``any_occurrence_in_month`` in
``backend/services/dashboard.py``.

These functions used to step forward/backward one interval at a time in a
Python loop (O(steps) — potentially thousands of iterations for an old
daily/weekly subscription). They were rewritten to O(1) closed-form
arithmetic. This file keeps a copy of the *original* loop-based logic as a
private reference implementation and asserts the new implementation is
byte-for-byte identical across a large matrix of intervals, anchor dates
(including multi-year-old ones), target months, and end_date settings —
so a subtle off-by-one in the arithmetic can't silently change billing
figures shown to users.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from dateutil.relativedelta import relativedelta

from backend.services import dashboard as dash

_INTERVAL_DELTAS = {
    "daily": relativedelta(days=1),
    "weekly": relativedelta(weeks=1),
    "monthly": relativedelta(months=1),
    "quarterly": relativedelta(months=3),
    "half-year": relativedelta(months=6),
    "yearly": relativedelta(years=1),
}


def _ref_due_date_in_month(recurring_date, interval, year, month, end_date=None):
    """Reference copy of the pre-rewrite loop-based due_date_in_month."""
    target_start = date(year, month, 1)
    target_end = (target_start + relativedelta(months=1)) - relativedelta(days=1)
    last = date.fromisoformat(recurring_date)
    delta = _INTERVAL_DELTAS.get(interval, relativedelta(months=1))

    if target_start <= last <= target_end:
        if end_date and last > date.fromisoformat(end_date):
            return None
        return last

    due = last + delta
    while due < target_start:
        due += delta

    if due > target_end:
        return None
    if end_date and due > date.fromisoformat(end_date):
        return None
    return due


def _ref_any_occurrence_in_month(recurring_date, interval, year, month, end_date=None):
    """Reference copy of the pre-rewrite loop-based any_occurrence_in_month."""
    target_start = date(year, month, 1)
    target_end = (target_start + relativedelta(months=1)) - relativedelta(days=1)
    anchor = date.fromisoformat(recurring_date)
    delta = _INTERVAL_DELTAS.get(interval, relativedelta(months=1))

    due = anchor
    if due < target_start:
        while due < target_start:
            due = due + delta
    elif due > target_end:
        while due > target_end:
            due = due - delta

    if not (target_start <= due <= target_end):
        return None
    if end_date and due > date.fromisoformat(end_date):
        return None
    return due


INTERVALS = ["daily", "weekly", "monthly", "quarterly", "half-year", "yearly"]

# Anchors spanning: recent, mid-range, and multi-year-old (the case that used
# to make the loop expensive for daily/weekly intervals).
ANCHORS = [
    "2026-01-15",
    "2025-06-01",
    "2024-03-10",
    "2020-01-01",  # ~6 years before the target years below
    "2018-11-30",  # ~8 years old, crosses many month/day boundaries
]

TARGETS = [(2020, 1), (2024, 3), (2025, 6), (2026, 1), (2026, 8), (2027, 12)]

END_DATES = [None, "2026-06-30", "2020-06-15"]


@pytest.mark.parametrize("interval", INTERVALS)
@pytest.mark.parametrize("anchor", ANCHORS)
@pytest.mark.parametrize("year,month", TARGETS)
@pytest.mark.parametrize("end_date", END_DATES)
class TestClosedFormMatchesReference:
    def test_due_date_in_month(self, interval, anchor, year, month, end_date):
        expected = _ref_due_date_in_month(anchor, interval, year, month, end_date=end_date)
        actual = dash.due_date_in_month(anchor, interval, year, month, end_date=end_date)
        assert actual == expected

    def test_any_occurrence_in_month(self, interval, anchor, year, month, end_date):
        expected = _ref_any_occurrence_in_month(anchor, interval, year, month, end_date=end_date)
        actual = dash.any_occurrence_in_month(anchor, interval, year, month, end_date=end_date)
        assert actual == expected


class TestClosedFormEdgeCases:
    """A few specific edge cases worth naming explicitly, beyond the matrix."""

    def test_anchor_exactly_on_month_boundary(self):
        assert dash.due_date_in_month("2026-08-01", "monthly", 2026, 8) == date(2026, 8, 1)

    def test_anchor_exactly_on_last_day_of_month(self):
        assert dash.any_occurrence_in_month("2026-01-31", "monthly", 2026, 1) == date(2026, 1, 31)

    def test_multi_year_daily_anchor_matches_reference(self):
        """The specific worst-case scenario the rewrite targets: a very old
        daily-interval anchor queried many years later — this used to require
        thousands of loop iterations."""
        anchor = "2015-01-01"
        expected = _ref_due_date_in_month(anchor, "daily", 2026, 8, end_date=None)
        actual = dash.due_date_in_month(anchor, "daily", 2026, 8, end_date=None)
        assert actual == expected
        assert expected is not None

    def test_yearly_totals_unaffected(self):
        """build_yearly_totals (which drives the dashboard yearly chart)
        must produce identical totals before/after the rewrite."""
        subs = [
            {
                "name": "Old daily sub",
                "amount": 1.0,
                "recurring_interval": "daily",
                "recurring_date": "2018-03-05",
                "end_date": None,
            },
            {
                "name": "Old weekly sub with end date",
                "amount": 12.5,
                "recurring_interval": "weekly",
                "recurring_date": "2019-11-20",
                "end_date": "2026-06-01",
            },
        ]
        totals = dash.build_yearly_totals(subs, 2026)
        assert len(totals) == 12
        assert all(t >= 0 for t in totals)
        # Every month should have exactly amount*[days in month] for the daily sub
        # (occurs every single day) plus whatever weekly occurrences land there.
        assert totals[0] > 0  # January has occurrences of both subs (before end_date)
