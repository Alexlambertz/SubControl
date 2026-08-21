"""
Tests for the dashboard service and /api/dashboard endpoint.

Covers: average-monthly conversion for each interval, real-monthly
        next-due-date scoping, bucket/category filtering, empty results.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_bucket(client: AsyncClient, name: str) -> str:
    r = await client.post("/api/buckets", json={"name": name})
    return r.json()["id"]


async def _make_sub(
    client: AsyncClient,
    bucket_id: str,
    *,
    name: str = "Sub",
    interval: str = "monthly",
    recurring_date: str = "2024-01-15",
    end_date: str | None = None,
    amount: float = 10.0,
    currency: str = "EUR",
    category: str | None = None,
) -> dict:
    payload = dict(
        name=name,
        provider_name=name,
        recurring_interval=interval,
        recurring_date=recurring_date,
        amount=amount,
        currency=currency,
    )
    if end_date:
        payload["end_date"] = end_date
    if category:
        payload["category_name"] = category
    r = await client.post(f"/api/buckets/{bucket_id}/subscriptions", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Unit tests for the conversion service (no HTTP)
# ---------------------------------------------------------------------------


class TestMonthlyConversionService:
    def test_monthly_unchanged(self) -> None:
        from backend.services.dashboard import to_monthly_average
        assert to_monthly_average(10.0, "monthly") == pytest.approx(10.0)

    def test_daily_times_30(self) -> None:
        from backend.services.dashboard import to_monthly_average
        assert to_monthly_average(1.0, "daily") == pytest.approx(30.0)

    def test_weekly_times_4_33(self) -> None:
        from backend.services.dashboard import to_monthly_average
        assert to_monthly_average(10.0, "weekly") == pytest.approx(43.3, rel=0.01)

    def test_quarterly_divided_by_3(self) -> None:
        from backend.services.dashboard import to_monthly_average
        assert to_monthly_average(30.0, "quarterly") == pytest.approx(10.0)

    def test_half_year_divided_by_6(self) -> None:
        from backend.services.dashboard import to_monthly_average
        assert to_monthly_average(60.0, "half-year") == pytest.approx(10.0)

    def test_yearly_divided_by_12(self) -> None:
        from backend.services.dashboard import to_monthly_average
        assert to_monthly_average(120.0, "yearly") == pytest.approx(10.0)


class TestAnyOccurrenceInMonth:
    def test_anchor_month_itself(self) -> None:
        from backend.services.dashboard import any_occurrence_in_month
        from datetime import date
        # Anchor is in March — March must return a result
        result = any_occurrence_in_month("2025-03-10", "monthly", 2025, 3)
        assert result == date(2025, 3, 10)

    def test_future_month_from_anchor(self) -> None:
        from backend.services.dashboard import any_occurrence_in_month
        from datetime import date
        result = any_occurrence_in_month("2025-01-15", "monthly", 2025, 4)
        assert result == date(2025, 4, 15)

    def test_past_month_before_anchor(self) -> None:
        from backend.services.dashboard import any_occurrence_in_month
        from datetime import date
        # Anchor June → January should also have an occurrence
        result = any_occurrence_in_month("2025-06-15", "monthly", 2025, 1)
        assert result == date(2025, 1, 15)

    def test_yearly_no_occurrence_in_off_month(self) -> None:
        from backend.services.dashboard import any_occurrence_in_month
        # Yearly sub anchored June 2024 → only June 2025 in 2025, not July
        result = any_occurrence_in_month("2024-06-01", "yearly", 2025, 7)
        assert result is None

    def test_quarterly_occurrence(self) -> None:
        from backend.services.dashboard import any_occurrence_in_month
        from datetime import date
        # Anchor Jan 15, quarterly → Apr 15 next, Oct 15 back-stepping from anchor
        result = any_occurrence_in_month("2025-01-15", "quarterly", 2025, 10)
        assert result == date(2025, 10, 15)


class TestNextDueDateService:
    def test_next_due_monthly(self) -> None:
        from backend.services.dashboard import next_due_date
        from datetime import date
        # Last payment 2024-01-15 → next due 2024-02-15
        result = next_due_date("2024-01-15", "monthly")
        assert result == date(2024, 2, 15)

    def test_next_due_yearly(self) -> None:
        from backend.services.dashboard import next_due_date
        from datetime import date
        result = next_due_date("2024-03-10", "yearly")
        assert result == date(2025, 3, 10)

    def test_next_due_weekly(self) -> None:
        from backend.services.dashboard import next_due_date
        from datetime import date
        result = next_due_date("2024-01-01", "weekly")
        assert result == date(2024, 1, 8)

    def test_next_due_quarterly(self) -> None:
        from backend.services.dashboard import next_due_date
        from datetime import date
        result = next_due_date("2024-01-15", "quarterly")
        assert result == date(2024, 4, 15)


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestDashboardEndpoint:
    async def test_empty_dashboard_returns_zeros(self, client: AsyncClient) -> None:
        resp = await client.get("/api/dashboard")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_monthly"] == pytest.approx(0.0)
        assert body["subscriptions"] == []

    async def test_average_mode_sums_correctly(self, client: AsyncClient) -> None:
        bid = await _make_bucket(client, "DashAvg")
        # 10 EUR/month + 120 EUR/year (= 10/month) = 20/month
        await _make_sub(client, bid, name="A", interval="monthly", amount=10.0)
        await _make_sub(client, bid, name="B", interval="yearly", amount=120.0)

        resp = await client.get("/api/dashboard?mode=average")
        body = resp.json()
        assert body["total_monthly"] == pytest.approx(20.0, rel=0.01)

    async def test_real_mode_filters_by_month(self, client: AsyncClient) -> None:
        bid = await _make_bucket(client, "DashReal")
        # Last payment 2024-01-15 → next due 2024-02-15 (in February)
        await _make_sub(
            client, bid, name="Feb", interval="monthly",
            recurring_date="2024-01-15", amount=10.0
        )
        # Last payment 2024-03-01 → next due 2024-04-01 (not in February)
        await _make_sub(
            client, bid, name="Apr", interval="monthly",
            recurring_date="2024-03-01", amount=20.0
        )

        resp = await client.get("/api/dashboard?mode=real&month=2024-02")
        body = resp.json()
        names = [s["name"] for s in body["subscriptions"]]
        assert "Feb" in names
        assert "Apr" not in names

    async def test_real_mode_monthly_recurs_every_month(self, client: AsyncClient) -> None:
        """A monthly subscription paid in Jan must appear in Feb, Mar, Jun, etc."""
        bid = await _make_bucket(client, "DashRecur")
        # Last payment 2024-01-15 — next occurrences: Feb, Mar, Apr, May, Jun …
        await _make_sub(
            client, bid, name="Monthly", interval="monthly",
            recurring_date="2024-01-15", amount=10.0
        )

        for month in ("2024-02", "2024-03", "2024-06", "2025-01"):
            resp = await client.get(f"/api/dashboard?mode=real&month={month}")
            body = resp.json()
            names = [s["name"] for s in body["subscriptions"]]
            assert "Monthly" in names, f"Expected 'Monthly' in {month}, got {names}"

    async def test_real_mode_yearly_only_in_anniversary_month(self, client: AsyncClient) -> None:
        """A yearly subscription paid 2024-03-10 appears in 2025-03 but not 2025-04."""
        bid = await _make_bucket(client, "DashYearly")
        await _make_sub(
            client, bid, name="Annual", interval="yearly",
            recurring_date="2024-03-10", amount=100.0
        )

        # Should appear in anniversary month 2025-03
        resp = await client.get("/api/dashboard?mode=real&month=2025-03")
        names = [s["name"] for s in resp.json()["subscriptions"]]
        assert "Annual" in names

        # Should NOT appear in adjacent month 2025-04
        resp = await client.get("/api/dashboard?mode=real&month=2025-04")
        names = [s["name"] for s in resp.json()["subscriptions"]]
        assert "Annual" not in names

    async def test_filter_by_bucket(self, client: AsyncClient) -> None:
        bid_a = await _make_bucket(client, "DashBucketA")
        bid_b = await _make_bucket(client, "DashBucketB")
        await _make_sub(client, bid_a, name="InA", amount=5.0)
        await _make_sub(client, bid_b, name="InB", amount=100.0)

        resp = await client.get(f"/api/dashboard?mode=average&bucket_id={bid_a}")
        body = resp.json()
        assert body["total_monthly"] == pytest.approx(5.0)

    async def test_real_mode_uses_created_at_when_no_recurring_date(self, client: AsyncClient) -> None:
        """
        When recurring_date is NULL the subscription's created_at date is used
        as the billing anchor so it still appears in the real-monthly dashboard.
        """
        from datetime import date
        from dateutil.relativedelta import relativedelta

        bid = await _make_bucket(client, "DashNoDate")
        # Create without recurring_date — SQLite sets created_at = datetime('now')
        r = await client.post(
            f"/api/buckets/{bid}/subscriptions",
            json={
                "name": "NoDate",
                "provider_name": "NoDate",
                "recurring_interval": "monthly",
                "amount": 15.0,
                "currency": "EUR",
                # recurring_date intentionally omitted
            },
        )
        assert r.status_code == 201

        # A monthly sub created today should recur next month
        today = date.today()
        next_month = (today + relativedelta(months=1)).strftime("%Y-%m")

        resp = await client.get(f"/api/dashboard?mode=real&month={next_month}")
        names = [s["name"] for s in resp.json()["subscriptions"]]
        assert "NoDate" in names, (
            f"Expected 'NoDate' to appear in {next_month} dashboard, got {names}"
        )

    async def test_real_mode_excludes_payment_after_end_date(self, client: AsyncClient) -> None:
        """Payment due date falls after end_date → subscription not shown."""
        bid = await _make_bucket(client, "DashEndDateExclude")
        # Last paid 2024-01-15, next due 2024-02-15; but subscription ended 2024-02-10
        await _make_sub(
            client, bid, name="Ended", interval="monthly",
            recurring_date="2024-01-15", end_date="2024-02-10", amount=10.0
        )
        resp = await client.get("/api/dashboard?mode=real&month=2024-02")
        names = [s["name"] for s in resp.json()["subscriptions"]]
        assert "Ended" not in names, f"Expected 'Ended' absent from 2024-02, got {names}"

    async def test_real_mode_includes_payment_on_end_date(self, client: AsyncClient) -> None:
        """Payment due exactly on end_date → included (inclusive boundary)."""
        bid = await _make_bucket(client, "DashEndDateInclusive")
        # Last paid 2024-01-15, next due 2024-02-15; end_date is exactly 2024-02-15
        await _make_sub(
            client, bid, name="LastDay", interval="monthly",
            recurring_date="2024-01-15", end_date="2024-02-15", amount=10.0
        )
        resp = await client.get("/api/dashboard?mode=real&month=2024-02")
        names = [s["name"] for s in resp.json()["subscriptions"]]
        assert "LastDay" in names, f"Expected 'LastDay' in 2024-02, got {names}"

    async def test_real_mode_shows_payment_before_end_date(self, client: AsyncClient) -> None:
        """Subscription with a future end_date still appears in earlier months."""
        bid = await _make_bucket(client, "DashEndDateFuture")
        await _make_sub(
            client, bid, name="Active", interval="monthly",
            recurring_date="2024-01-15", end_date="2025-12-31", amount=10.0
        )
        resp = await client.get("/api/dashboard?mode=real&month=2024-06")
        names = [s["name"] for s in resp.json()["subscriptions"]]
        assert "Active" in names, f"Expected 'Active' in 2024-06, got {names}"

    async def test_real_mode_anchor_in_target_month(self, client: AsyncClient) -> None:
        """
        When recurring_date falls within the queried month, the subscription must
        appear in the Real Monthly total (regression: due_date_in_month used to
        advance by one interval first, landing in the *next* month and returning None).
        """
        bid = await _make_bucket(client, "DashAnchorInMonth")
        # Last payment 2026-06-01 — the billing date for June IS June 1 itself
        await _make_sub(
            client, bid, name="JuneSub", interval="monthly",
            recurring_date="2026-06-01", amount=15.0
        )
        resp = await client.get("/api/dashboard?mode=real&month=2026-06")
        body = resp.json()
        names = [s["name"] for s in body["subscriptions"]]
        assert "JuneSub" in names, f"Expected 'JuneSub' in 2026-06, got {names}"
        assert body["total_monthly"] == 15.0

    async def test_average_mode_excludes_ended_subscription(self, client: AsyncClient) -> None:
        """Subscription with end_date before the queried month is excluded from average total."""
        bid = await _make_bucket(client, "DashAvgEnded")
        # This sub ended in January — querying February should exclude it
        await _make_sub(
            client, bid, name="Old", interval="monthly",
            recurring_date="2024-01-15", end_date="2024-01-31", amount=50.0
        )
        # This sub is still active
        await _make_sub(
            client, bid, name="Active", interval="monthly",
            recurring_date="2024-01-15", amount=20.0
        )
        resp = await client.get("/api/dashboard?mode=average&month=2024-02")
        body = resp.json()
        assert body["total_monthly"] == pytest.approx(20.0)
        names = [s["name"] for s in body["subscriptions"]]
        assert "Old" not in names
        assert "Active" in names

    async def test_average_mode_no_month_includes_all(self, client: AsyncClient) -> None:
        """When no month param is given, all subscriptions appear regardless of end_date."""
        bid = await _make_bucket(client, "DashAvgNoMonth")
        await _make_sub(
            client, bid, name="Expired", interval="monthly",
            recurring_date="2020-01-01", end_date="2020-12-31", amount=10.0
        )
        await _make_sub(
            client, bid, name="Current", interval="monthly",
            recurring_date="2024-01-15", amount=20.0
        )
        resp = await client.get("/api/dashboard?mode=average")
        body = resp.json()
        assert body["total_monthly"] == pytest.approx(30.0)

    async def test_by_category_breakdown(self, client: AsyncClient) -> None:
        bid = await _make_bucket(client, "DashCat")
        await _make_sub(client, bid, name="S1", amount=10.0, category="Streaming")
        await _make_sub(client, bid, name="S2", amount=5.0, category="Streaming")
        await _make_sub(client, bid, name="S3", amount=20.0, category="Haushalt")

        resp = await client.get("/api/dashboard?mode=average")
        body = resp.json()
        by_cat = {c["category"]: c["total"] for c in body["by_category"]}
        assert by_cat.get("Streaming", 0) == pytest.approx(15.0)
        assert by_cat.get("Haushalt", 0) == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# Yearly dashboard endpoint
# ---------------------------------------------------------------------------


class TestYearlyDashboardEndpoint:
    async def test_returns_12_months(self, client: AsyncClient) -> None:
        resp = await client.get("/api/dashboard/yearly?year=2025")
        assert resp.status_code == 200
        body = resp.json()
        assert body["year"] == 2025
        assert len(body["months"]) == 12

    async def test_month_labels_correct(self, client: AsyncClient) -> None:
        resp = await client.get("/api/dashboard/yearly?year=2025")
        labels = [m["label"] for m in resp.json()["months"]]
        assert labels == ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    async def test_month_keys_correct(self, client: AsyncClient) -> None:
        resp = await client.get("/api/dashboard/yearly?year=2025")
        months_field = [m["month"] for m in resp.json()["months"]]
        assert months_field[0] == "2025-01"
        assert months_field[11] == "2025-12"

    async def test_empty_subscriptions_all_zeros(self, client: AsyncClient) -> None:
        resp = await client.get("/api/dashboard/yearly?year=2025")
        totals = [m["total"] for m in resp.json()["months"]]
        assert all(t == pytest.approx(0.0) for t in totals)

    async def test_monthly_sub_appears_every_month(self, client: AsyncClient) -> None:
        """A monthly subscription should contribute to every calendar month."""
        bid = await _make_bucket(client, "YearlyMonthly")
        await _make_sub(
            client, bid, name="Netflix",
            interval="monthly", recurring_date="2024-12-15", amount=9.99,
        )
        resp = await client.get("/api/dashboard/yearly?year=2025")
        totals = [m["total"] for m in resp.json()["months"]]
        assert all(t == pytest.approx(9.99) for t in totals)

    async def test_yearly_sub_appears_in_anniversary_month_only(
        self, client: AsyncClient
    ) -> None:
        """A yearly subscription only appears in its single anniversary month."""
        bid = await _make_bucket(client, "YearlyAnnual")
        # Paid 2024-06-01 → anniversary in 2025 is June 2025 only
        await _make_sub(
            client, bid, name="Adobe",
            interval="yearly", recurring_date="2024-06-01", amount=60.0,
        )
        resp = await client.get("/api/dashboard/yearly?year=2025")
        months = {m["label"]: m["total"] for m in resp.json()["months"]}
        assert months["Jun"] == pytest.approx(60.0)
        for label in ["Jan", "Feb", "Mar", "Apr", "May",
                      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]:
            assert months[label] == pytest.approx(0.0)

    async def test_past_months_shown_for_anchor_in_future(
        self, client: AsyncClient
    ) -> None:
        """
        A monthly subscription with anchor in June must appear in every month
        of the year — including January through May that precede the anchor.
        """
        bid = await _make_bucket(client, "YearlyPast")
        # Anchor is mid-year; earlier months should still be shown
        await _make_sub(
            client, bid, name="Sub",
            interval="monthly", recurring_date="2025-06-15", amount=10.0,
        )
        resp = await client.get("/api/dashboard/yearly?year=2025")
        months = {m["label"]: m["total"] for m in resp.json()["months"]}
        for label in ["Jan", "Feb", "Mar", "Apr", "May",
                      "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]:
            assert months[label] == pytest.approx(10.0), (
                f"{label} expected 10.0, got {months[label]}"
            )

    async def test_anchor_month_itself_is_included(
        self, client: AsyncClient
    ) -> None:
        """The month of the anchor date must appear in the yearly graph."""
        bid = await _make_bucket(client, "YearlyAnchorMonth")
        # Anchor is in March — March must show up
        await _make_sub(
            client, bid, name="Sub",
            interval="monthly", recurring_date="2025-03-10", amount=15.0,
        )
        resp = await client.get("/api/dashboard/yearly?year=2025")
        months = {m["label"]: m["total"] for m in resp.json()["months"]}
        assert months["Mar"] == pytest.approx(15.0)

    async def test_bucket_filter_is_respected(self, client: AsyncClient) -> None:
        bid_a = await _make_bucket(client, "YearlyBucketA")
        bid_b = await _make_bucket(client, "YearlyBucketB")
        await _make_sub(
            client, bid_a, name="InA",
            interval="monthly", recurring_date="2024-12-01", amount=5.0,
        )
        await _make_sub(
            client, bid_b, name="InB",
            interval="monthly", recurring_date="2024-12-01", amount=100.0,
        )
        resp = await client.get(f"/api/dashboard/yearly?year=2025&bucket_id={bid_a}")
        totals = [m["total"] for m in resp.json()["months"]]
        # Bucket A only → 5.0 per month, bucket B excluded
        assert all(t == pytest.approx(5.0) for t in totals)

    async def test_yearly_zeroes_months_after_end_date(self, client: AsyncClient) -> None:
        """Monthly sub ending 2025-03-31 → Jan/Feb/Mar show amount, Apr–Dec show zero."""
        bid = await _make_bucket(client, "YearlyEndDate")
        await _make_sub(
            client, bid, name="Short",
            interval="monthly", recurring_date="2024-12-01",
            end_date="2025-03-31", amount=10.0,
        )
        resp = await client.get("/api/dashboard/yearly?year=2025")
        months = {m["label"]: m["total"] for m in resp.json()["months"]}
        # Should appear in Jan, Feb, Mar (payment dates 2025-01-01, 2025-02-01, 2025-03-01)
        for label in ["Jan", "Feb", "Mar"]:
            assert months[label] == pytest.approx(10.0), (
                f"{label} expected 10.0, got {months[label]}"
            )
        # Apr (2025-04-01) > end_date (2025-03-31) → zero
        for label in ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]:
            assert months[label] == pytest.approx(0.0), (
                f"{label} expected 0.0, got {months[label]}"
            )

    async def test_year_param_required(self, client: AsyncClient) -> None:
        resp = await client.get("/api/dashboard/yearly")
        assert resp.status_code == 422

    async def test_invalid_year_rejected(self, client: AsyncClient) -> None:
        resp = await client.get("/api/dashboard/yearly?year=1999")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Insurances merged into the same dashboard totals as subscriptions
# ---------------------------------------------------------------------------


async def _make_insurance(
    client: AsyncClient,
    bucket_id: str,
    *,
    name: str = "Insurance",
    interval: str = "monthly",
    recurring_date: str = "2024-01-15",
    amount: float = 10.0,
    category: str | None = None,
) -> dict:
    payload = dict(
        name=name,
        insurer=name,
        recurring_interval=interval,
        recurring_date=recurring_date,
        amount=amount,
    )
    if category:
        payload["category_name"] = category
    r = await client.post(f"/api/buckets/{bucket_id}/insurances", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


class TestInsuranceDashboardIntegration:
    async def test_average_total_includes_insurance(self, client: AsyncClient) -> None:
        bid = await _make_bucket(client, "MixedAvg")
        await _make_sub(client, bid, name="Sub", interval="monthly", amount=10.0)
        await _make_insurance(client, bid, name="Ins", interval="monthly", amount=15.0)

        resp = await client.get("/api/dashboard?mode=average")
        body = resp.json()
        assert body["total_monthly"] == pytest.approx(25.0, rel=0.01)

        kinds = {s["name"]: s["kind"] for s in body["subscriptions"]}
        assert kinds["Sub"] == "subscription"
        assert kinds["Ins"] == "insurance"

    async def test_by_category_blends_subscriptions_and_insurances(
        self, client: AsyncClient
    ) -> None:
        bid = await _make_bucket(client, "MixedCategory")
        await _make_sub(client, bid, name="Sub", amount=10.0, category="Home")
        await _make_insurance(client, bid, name="Ins", amount=15.0, category="Home")

        resp = await client.get("/api/dashboard?mode=average")
        by_cat = {c["category"]: c["total"] for c in resp.json()["by_category"]}
        assert by_cat["Home"] == pytest.approx(25.0, rel=0.01)

    async def test_real_mode_includes_insurance_due_in_month(
        self, client: AsyncClient
    ) -> None:
        bid = await _make_bucket(client, "MixedReal")
        await _make_insurance(
            client, bid, name="Ins", interval="monthly",
            recurring_date="2024-01-15", amount=15.0,
        )
        resp = await client.get("/api/dashboard?mode=real&month=2024-02")
        names = [s["name"] for s in resp.json()["subscriptions"]]
        assert "Ins" in names

    async def test_yearly_totals_include_insurance(self, client: AsyncClient) -> None:
        bid = await _make_bucket(client, "MixedYearly")
        await _make_insurance(
            client, bid, name="Ins", interval="monthly",
            recurring_date="2025-01-01", amount=15.0,
        )
        resp = await client.get("/api/dashboard/yearly?year=2025")
        months = {m["label"]: m["total"] for m in resp.json()["months"]}
        assert months["Jan"] == pytest.approx(15.0)
