"""
Dashboard router.

Routes
------
GET /api/dashboard          — Subscription cost summary (single month).
GET /api/dashboard/yearly   — Real-cost totals for every month of a given year.

Query parameters
----------------
mode        : "average" (default) | "real"
month       : YYYY-MM  (required when mode=real; used to select the calendar month)
bucket_id   : filter to a single bucket
category_id : filter to a single category (monthly endpoint only)
year        : YYYY  (yearly endpoint)
"""

from __future__ import annotations

import calendar as _cal
import logging
import re
from typing import Optional

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.database import get_db
from backend.dependencies import CurrentUser, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["dashboard"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class SubscriptionSummaryItem(BaseModel):
    name: str
    monthly_amount: float
    currency: str
    category: str = "Uncategorized"


class CategoryTotal(BaseModel):
    category: str
    total: float


class DashboardResponse(BaseModel):
    total_monthly: float
    subscriptions: list[SubscriptionSummaryItem]
    by_category: list[CategoryTotal]


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    mode: str = Query("average", pattern="^(average|real)$"),
    month: Optional[str] = Query(
        None, description="YYYY-MM — required when mode=real"
    ),
    bucket_id: Optional[str] = Query(None),
    category_id: Optional[int] = Query(None),
    user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> DashboardResponse:
    """Return the dashboard cost summary."""
    if mode == "real":
        if month is None:
            raise HTTPException(
                status_code=422,
                detail="Query parameter 'month' (YYYY-MM) is required when mode=real",
            )
        if not re.match(r"^\d{4}-\d{2}$", month):
            raise HTTPException(
                status_code=422, detail="'month' must be in YYYY-MM format"
            )

    # Build dynamic WHERE clause — always scope to the user's accessible buckets
    conditions: list[str] = []
    params: list = []

    if not user.is_admin:
        conditions.append(
            "s.bucket_id IN (SELECT bucket_id FROM user_buckets WHERE user_id = ?)"
        )
        params.append(user.id)

    if bucket_id:
        # Verify the user actually has access to this specific bucket
        if not user.is_admin:
            async with db.execute(
                "SELECT 1 FROM user_buckets WHERE user_id = ? AND bucket_id = ?",
                (user.id, bucket_id),
            ) as cur:
                if await cur.fetchone() is None:
                    raise HTTPException(status_code=403, detail="Access denied to this bucket")
        conditions.append("s.bucket_id = ?")
        params.append(bucket_id)

    if category_id is not None:
        conditions.append("s.category_id = ?")
        params.append(category_id)

    where = " AND ".join(conditions) if conditions else "1=1"

    async with db.execute(
        f"""
        SELECT s.name, s.amount, s.currency,
               s.recurring_interval, s.recurring_date, s.end_date, s.created_at,
               c.name AS category_name
        FROM subscriptions s
        LEFT JOIN categories c ON s.category_id = c.id
        WHERE {where}
        """,
        params,
    ) as cur:
        rows = await cur.fetchall()

    subscriptions = [dict(r) for r in rows]

    from datetime import date as _date
    from backend.services.dashboard import build_average_summary, build_real_summary

    if mode == "average":
        reference_date = None
        if month and re.match(r"^\d{4}-\d{2}$", month):
            year_ref, mon_ref = int(month[:4]), int(month[5:7])
            reference_date = _date(year_ref, mon_ref, 1)
        summary = build_average_summary(subscriptions, reference_date=reference_date)
    else:
        year, mon = int(month[:4]), int(month[5:7])
        summary = build_real_summary(subscriptions, year, mon)

    return DashboardResponse(**summary)


# ---------------------------------------------------------------------------
# Yearly overview endpoint
# ---------------------------------------------------------------------------


class MonthTotal(BaseModel):
    month: str    # "2025-01"
    label: str    # "Jan"
    total: float


class YearlyDashboardResponse(BaseModel):
    year: int
    months: list[MonthTotal]


@router.get("/dashboard/yearly", response_model=YearlyDashboardResponse)
async def get_yearly_dashboard(
    year: int = Query(..., ge=2000, le=2100, description="Four-digit year"),
    bucket_id: Optional[str] = Query(None),
    user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> YearlyDashboardResponse:
    """
    Return real-monthly cost totals for every month of *year*.

    Subscriptions are fetched once and the real-monthly calculation is
    applied 12 times (one per calendar month) in Python — no 12× DB round-trips.
    """
    conditions: list[str] = []
    params: list = []

    if not user.is_admin:
        conditions.append(
            "s.bucket_id IN (SELECT bucket_id FROM user_buckets WHERE user_id = ?)"
        )
        params.append(user.id)

    if bucket_id:
        if not user.is_admin:
            async with db.execute(
                "SELECT 1 FROM user_buckets WHERE user_id = ? AND bucket_id = ?",
                (user.id, bucket_id),
            ) as cur:
                if await cur.fetchone() is None:
                    raise HTTPException(status_code=403, detail="Access denied to this bucket")
        conditions.append("s.bucket_id = ?")
        params.append(bucket_id)

    where = " AND ".join(conditions) if conditions else "1=1"

    async with db.execute(
        f"""
        SELECT s.name, s.amount, s.currency,
               s.recurring_interval, s.recurring_date, s.end_date, s.created_at,
               c.name AS category_name
        FROM subscriptions s
        LEFT JOIN categories c ON s.category_id = c.id
        WHERE {where}
        """,
        params,
    ) as cur:
        rows = await cur.fetchall()

    subscriptions = [dict(r) for r in rows]

    from backend.services.dashboard import build_yearly_totals

    totals = build_yearly_totals(subscriptions, year)   # 12 values, index 0 = Jan

    months: list[MonthTotal] = [
        MonthTotal(
            month=f"{year}-{m:02d}",
            label=_cal.month_abbr[m],
            total=totals[m - 1],
        )
        for m in range(1, 13)
    ]

    return YearlyDashboardResponse(year=year, months=months)
