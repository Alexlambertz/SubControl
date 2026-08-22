"""
Dashboard calculation service.

Two modes
---------
average
    Each subscription's amount is converted to an equivalent monthly figure
    regardless of the calendar month.  Useful for recurring cost overview.
    Subscriptions with an ``end_date`` before the reference month are excluded.

real
    Only subscriptions whose *next due date* falls within the queried
    calendar month are counted.  ``recurring_date`` is the **last payment date**;
    the service steps forward by the interval to find future due dates.
    Payments that would fall after ``end_date`` are excluded.

Conversion factors (average mode)
----------------------------------
daily       × 30
weekly      × (365/12 / 7) ≈ × 4.333
monthly     × 1
quarterly   ÷ 3
half-year   ÷ 6
yearly      ÷ 12
"""

from __future__ import annotations

from datetime import date, timedelta
from dateutil.relativedelta import relativedelta


# ---------------------------------------------------------------------------
# Conversion factors
# ---------------------------------------------------------------------------

_FACTORS: dict[str, float] = {
    "daily": 30.0,
    "weekly": 365.0 / 12.0 / 7.0,  # ≈ 4.333
    "monthly": 1.0,
    "quarterly": 1.0 / 3.0,
    "half-year": 1.0 / 6.0,
    "yearly": 1.0 / 12.0,
}


def to_monthly_average(amount: float, interval: str) -> float:
    """
    Convert *amount* billed at *interval* to an average monthly equivalent.

    Parameters
    ----------
    amount:
        The billing amount per interval.
    interval:
        One of ``daily``, ``weekly``, ``monthly``, ``quarterly``,
        ``half-year``, ``yearly``.

    Returns
    -------
    The average monthly amount.
    """
    factor = _FACTORS.get(interval, 1.0)
    return amount * factor


# ---------------------------------------------------------------------------
# Next-due-date calculation
# ---------------------------------------------------------------------------

_INTERVAL_DELTAS = {
    "daily": relativedelta(days=1),
    "weekly": relativedelta(weeks=1),
    "monthly": relativedelta(months=1),
    "quarterly": relativedelta(months=3),
    "half-year": relativedelta(months=6),
    "yearly": relativedelta(years=1),
}


def next_due_date(recurring_date: str, interval: str) -> date:
    """
    Compute the *next* payment date given the *last* payment date and interval.

    Parameters
    ----------
    recurring_date:
        ISO-8601 date string of the last payment (e.g. ``"2024-01-15"``).
    interval:
        Billing interval string.

    Returns
    -------
    The next due ``date`` (one step ahead of ``recurring_date``).
    """
    last = date.fromisoformat(recurring_date)
    delta = _INTERVAL_DELTAS.get(interval, relativedelta(months=1))
    return last + delta


# Fixed-length intervals: day-based ones have a constant day-count, month-based
# ones have a constant month-count. This lets "how many steps from anchor to
# reach/pass target" be computed in O(1) instead of looping one step at a time
# (the old approach could take thousands of iterations for an old daily/weekly
# anchor queried many years later).
_INTERVAL_DAY_LENGTHS = {"daily": 1, "weekly": 7}
_INTERVAL_MONTH_LENGTHS = {"monthly": 1, "quarterly": 3, "half-year": 6, "yearly": 12}


def _step_forward(anchor: date, interval: str, target: date, *, min_steps: int) -> date:
    """
    Smallest ``anchor + n*interval`` that is ``>= target``, with ``n >= min_steps``.

    Mirrors the pre-rewrite loop pattern: ``min_steps=1`` replicates
    "start from anchor+delta, then keep adding delta while < target"
    (used by ``due_date_in_month``); ``min_steps=0`` replicates
    "start from anchor itself, then keep adding delta while < target"
    (used by ``any_occurrence_in_month``).
    """
    if interval in _INTERVAL_DAY_LENGTHS:
        step_days = _INTERVAL_DAY_LENGTHS[interval]
        diff_days = (target - anchor).days
        n = max(min_steps, -(-diff_days // step_days))  # ceiling division
        return anchor + timedelta(days=n * step_days)

    step_months = _INTERVAL_MONTH_LENGTHS.get(interval, 1)
    if anchor.day >= 29:
        # Stepping through a short month (e.g. February) clamps the day of
        # month down (30th -> 28th), and — because relativedelta re-derives
        # from whichever date is *current*, not the original anchor — that
        # clamp sticks for every later step too. Direct "anchor + n months"
        # arithmetic can't reproduce that path-dependent clamping, so fall
        # back to the legacy step-by-step loop for this narrow case (at most
        # ~12 iterations to hit the first short month, then it degenerates
        # into the simple no-clamp case). Day-based intervals and the
        # anchor.day <= 28 case above never clamp, so they stay O(1).
        delta = _INTERVAL_DELTAS[interval]
        due = anchor if min_steps == 0 else anchor + delta
        while due < target:
            due += delta
        return due

    month_diff = (target.year - anchor.year) * 12 + (target.month - anchor.month)
    n = max(min_steps, -(-month_diff // step_months))  # ceiling division
    return anchor + relativedelta(months=n * step_months)


def _step_backward(anchor: date, interval: str, target: date) -> date:
    """
    Largest ``anchor - n*interval`` (``n >= 0``) that is ``<= anchor`` and
    brings the date back to ``<= target`` — mirrors "keep subtracting delta
    while > target", starting from ``anchor`` itself (n can be 0).
    """
    if interval in _INTERVAL_DAY_LENGTHS:
        step_days = _INTERVAL_DAY_LENGTHS[interval]
        diff_days = (anchor - target).days
        n = max(0, -(-diff_days // step_days))
        return anchor - timedelta(days=n * step_days)

    step_months = _INTERVAL_MONTH_LENGTHS.get(interval, 1)
    if anchor.day >= 29:
        # See _step_forward — same path-dependent clamping issue applies
        # when stepping backward through a short month.
        delta = _INTERVAL_DELTAS[interval]
        due = anchor
        while due > target:
            due -= delta
        return due

    month_diff = (anchor.year - target.year) * 12 + (anchor.month - target.month)
    n = max(0, -(-month_diff // step_months))
    return anchor - relativedelta(months=n * step_months)


def due_date_in_month(
    recurring_date: str,
    interval: str,
    year: int,
    month: int,
    end_date: str | None = None,
) -> date | None:
    """
    Return the due date that falls within *year*-*month*, or ``None``.

    ``recurring_date`` is the **last payment date**.  The nearest occurrence
    strictly after it (or the anchor itself, if already within the target
    month) is checked against the target month.

    If *end_date* is set and the computed due date would fall after it, ``None``
    is returned (the subscription has ended).  A payment due on *end_date* itself
    is considered valid (inclusive upper bound).

    Parameters
    ----------
    recurring_date:
        ISO-8601 date string of the last payment.
    interval:
        Billing interval string.
    year, month:
        The calendar month to check.
    end_date:
        Optional ISO-8601 date string; billing stops after this date.

    Returns
    -------
    The ``date`` of the payment within that month, or ``None`` if no payment
    falls in that month (or would fall after *end_date*).
    """
    target_start = date(year, month, 1)
    target_end = (target_start + relativedelta(months=1)) - relativedelta(days=1)

    last = date.fromisoformat(recurring_date)

    # If the anchor (last payment) itself falls in the target month, that IS
    # the billing date for this month — no need to step forward.
    if target_start <= last <= target_end:
        if end_date and last > date.fromisoformat(end_date):
            return None
        return last

    due = _step_forward(last, interval, target_start, min_steps=1)

    if due > target_end:
        return None
    if end_date and due > date.fromisoformat(end_date):
        return None
    return due


def any_occurrence_in_month(
    recurring_date: str,
    interval: str,
    year: int,
    month: int,
    end_date: str | None = None,
) -> date | None:
    """
    Return the occurrence of the billing cycle that falls within *year*-*month*,
    or ``None`` if no occurrence falls there.

    Unlike :func:`due_date_in_month`, this searches **both** past and future
    occurrences relative to the anchor so that subscriptions appear in every
    month they were (or will be) billed, not only from the anchor forward.

    If *end_date* is set and the computed occurrence would fall after it, ``None``
    is returned.  An occurrence on *end_date* itself is valid (inclusive).

    Parameters
    ----------
    recurring_date:
        ISO-8601 date string of a known payment (anchor).
    interval:
        Billing interval string.
    year, month:
        The calendar month to check.
    end_date:
        Optional ISO-8601 date string; billing stops after this date.
    """
    target_start = date(year, month, 1)
    target_end = (target_start + relativedelta(months=1)) - relativedelta(days=1)

    anchor = date.fromisoformat(recurring_date)

    if anchor < target_start:
        due = _step_forward(anchor, interval, target_start, min_steps=0)
    elif anchor > target_end:
        due = _step_backward(anchor, interval, target_end)
    else:
        due = anchor

    if not (target_start <= due <= target_end):
        return None
    if end_date and due > date.fromisoformat(end_date):
        return None
    return due


def build_yearly_totals_split(subscriptions: list[dict], year: int) -> list[dict]:
    """
    Compute the real-cost total for each of the 12 months in *year*, split
    into a ``baseline`` (monthly-interval subscriptions, which recur every
    month) and an ``on_top`` figure (everything else — yearly/quarterly/etc.
    charges landing as spikes in the specific months they're due).

    Uses :func:`any_occurrence_in_month` when an explicit ``recurring_date``
    is set (``recurring_date`` = last payment date), so the subscription appears
    in every month it is billed — both before and after the anchor date.
    Months after ``end_date`` receive 0.

    When only ``created_at`` is available (no explicit ``recurring_date``),
    :func:`due_date_in_month` is used instead so that future occurrences are
    shown but no phantom payments before the subscription existed are invented.

    Returns
    -------
    A list of 12 ``{baseline, on_top, total}`` dicts, index 0 = January …
    index 11 = December.
    """
    baseline = [0.0] * 12
    on_top = [0.0] * 12
    for sub in subscriptions:
        recurring_date = sub.get("recurring_date")
        end_date = sub.get("end_date") or None
        if recurring_date:
            anchor = recurring_date[:10]
            find = any_occurrence_in_month
        else:
            created = sub.get("created_at")
            if not created:
                continue
            anchor = created[:10]
            find = due_date_in_month     # forward-only: sub didn't exist before creation

        bucket = baseline if sub["recurring_interval"] == "monthly" else on_top
        for m in range(1, 13):
            if find(anchor, sub["recurring_interval"], year, m, end_date=end_date):
                bucket[m - 1] += sub["amount"]

    return [
        {
            "baseline": round(baseline[m], 2),
            "on_top": round(on_top[m], 2),
            "total": round(baseline[m] + on_top[m], 2),
        }
        for m in range(12)
    ]


# ---------------------------------------------------------------------------
# Dashboard summary builder
# ---------------------------------------------------------------------------


def build_average_summary(
    subscriptions: list[dict],
    reference_date: date | None = None,
) -> dict:
    """
    Compute average-monthly totals from a list of subscription dicts.

    Each dict must have: ``name``, ``amount``, ``currency``,
    ``recurring_interval``, ``category_name`` (may be None).

    Parameters
    ----------
    subscriptions:
        List of subscription dicts from the database.
    reference_date:
        If given (typically the first day of the selected month), subscriptions
        whose ``end_date`` is strictly before this date are excluded — they have
        already stopped billing.  When ``None``, all subscriptions are included
        (backward-compatible behaviour when no month is specified).

    Returns
    -------
    A dict with keys:
    - ``total_monthly``  — sum of all monthly equivalents
    - ``subscriptions``  — list of ``{name, monthly_amount, currency}``
    - ``by_category``    — list of ``{category, total}``
    """
    items = []
    by_cat: dict[str, float] = {}
    total = 0.0

    for sub in subscriptions:
        # Skip subscriptions that have ended before the reference month
        if reference_date is not None:
            end_date_str = sub.get("end_date")
            if end_date_str and date.fromisoformat(end_date_str) < reference_date:
                continue

        monthly = to_monthly_average(sub["amount"], sub["recurring_interval"])
        total += monthly
        cat = sub.get("category_name") or "Uncategorized"
        items.append(
            {
                "name": sub["name"],
                "monthly_amount": round(monthly, 2),
                "currency": sub["currency"],
                "category": cat,
                "kind": sub.get("kind", "subscription"),
                "recurring_interval": sub["recurring_interval"],
                "is_baseline": sub["recurring_interval"] == "monthly",
            }
        )
        by_cat[cat] = by_cat.get(cat, 0.0) + monthly

    return {
        "total_monthly": round(total, 2),
        "subscriptions": items,
        "by_category": [
            {"category": k, "total": round(v, 2)} for k, v in sorted(by_cat.items())
        ],
    }


def build_real_summary(subscriptions: list[dict], year: int, month: int) -> dict:
    """
    Compute real-monthly totals: only subscriptions due in *year*-*month*.

    ``recurring_date`` is the **last payment date**.  The next payment is
    computed by stepping forward in ``recurring_interval`` increments.  Only
    payments that fall within the target calendar month and on or before
    ``end_date`` (if set) are included.

    When ``recurring_date`` is absent the subscription's ``created_at`` date is
    used as the anchor (forward-only search).

    Returns the same structure as :func:`build_average_summary`.
    """
    items = []
    by_cat: dict[str, float] = {}
    total = 0.0

    for sub in subscriptions:
        # Prefer the explicit last-payment date; fall back to the creation date.
        anchor = sub.get("recurring_date") or sub.get("created_at")
        if not anchor:
            continue
        # created_at is stored as a datetime string ("YYYY-MM-DD HH:MM:SS");
        # take just the date portion so fromisoformat() works in both cases.
        anchor = anchor[:10]
        end_date = sub.get("end_date") or None

        due = due_date_in_month(anchor, sub["recurring_interval"], year, month, end_date=end_date)

        if due is not None:
            total += sub["amount"]
            cat = sub.get("category_name") or "Uncategorized"
            items.append(
                {
                    "name": sub["name"],
                    "monthly_amount": round(sub["amount"], 2),
                    "currency": sub["currency"],
                    "category": cat,
                    "kind": sub.get("kind", "subscription"),
                    "recurring_interval": sub["recurring_interval"],
                    "is_baseline": sub["recurring_interval"] == "monthly",
                }
            )
            by_cat[cat] = by_cat.get(cat, 0.0) + sub["amount"]

    return {
        "total_monthly": round(total, 2),
        "subscriptions": items,
        "by_category": [
            {"category": k, "total": round(v, 2)} for k, v in sorted(by_cat.items())
        ],
    }
