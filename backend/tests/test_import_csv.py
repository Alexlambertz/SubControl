"""
Tests for POST /api/buckets/{bucket_id}/subscriptions/import (CSV bulk import).
"""

from __future__ import annotations

import io
import pytest
from httpx import AsyncClient


async def _make_bucket(client: AsyncClient, name: str) -> str:
    r = await client.post("/api/buckets", json={"name": name})
    return r.json()["id"]


def _csv_file(content: str) -> dict:
    """Create a multipart file upload dict from CSV string content."""
    return {"file": ("import.csv", io.BytesIO(content.encode()), "text/csv")}


VALID_CSV = """\
name,provider,recurring_interval,recurring_date,amount,currency,category
Netflix,Netflix,monthly,2024-01-15,9.99,EUR,Streaming
Spotify,Spotify,monthly,2024-01-01,4.99,EUR,Music
Amazon Prime,Amazon,yearly,2024-06-01,89.99,USD,Shopping
"""


class TestCsvImportValid:
    async def test_valid_csv_returns_200(self, client: AsyncClient) -> None:
        bid = await _make_bucket(client, "ImportBucket1")
        resp = await client.post(
            f"/api/buckets/{bid}/subscriptions/import",
            files=_csv_file(VALID_CSV),
        )
        assert resp.status_code == 200

    async def test_valid_csv_imports_all_rows(self, client: AsyncClient) -> None:
        bid = await _make_bucket(client, "ImportBucket2")
        resp = await client.post(
            f"/api/buckets/{bid}/subscriptions/import",
            files=_csv_file(VALID_CSV),
        )
        body = resp.json()
        assert body["imported"] == 3
        assert body["failed"] == []

    async def test_subscriptions_appear_in_list(self, client: AsyncClient) -> None:
        bid = await _make_bucket(client, "ImportBucket3")
        await client.post(
            f"/api/buckets/{bid}/subscriptions/import",
            files=_csv_file(VALID_CSV),
        )
        list_resp = await client.get(f"/api/buckets/{bid}/subscriptions")
        names = [s["name"] for s in list_resp.json()]
        assert "Netflix" in names
        assert "Spotify" in names

    async def test_provider_auto_created(self, client: AsyncClient) -> None:
        bid = await _make_bucket(client, "ImportProvider")
        csv_content = (
            "name,provider,recurring_interval,recurring_date,amount,currency\n"
            "TestSub,UniqueProviderXYZ,monthly,2024-01-01,5.0,EUR\n"
        )
        await client.post(
            f"/api/buckets/{bid}/subscriptions/import",
            files=_csv_file(csv_content),
        )
        providers_resp = await client.get("/api/providers")
        names = [p["name"] for p in providers_resp.json()]
        assert "UniqueProviderXYZ" in names

    async def test_currency_defaults_to_eur_when_omitted(
        self, client: AsyncClient
    ) -> None:
        bid = await _make_bucket(client, "ImportCurrency")
        csv_content = (
            "name,provider,recurring_interval,recurring_date,amount\n"
            "TestSub,X,monthly,2024-01-01,5.0\n"
        )
        resp = await client.post(
            f"/api/buckets/{bid}/subscriptions/import",
            files=_csv_file(csv_content),
        )
        assert resp.json()["imported"] == 1
        subs_resp = await client.get(f"/api/buckets/{bid}/subscriptions")
        assert subs_resp.json()[0]["currency"] == "EUR"


class TestCsvImportErrors:
    async def test_missing_required_field_reports_row_error(
        self, client: AsyncClient
    ) -> None:
        bid = await _make_bucket(client, "ImportErr1")
        csv_content = (
            "name,provider,recurring_interval,recurring_date,amount\n"
            "Valid,X,monthly,2024-01-01,5.0\n"
            "MissingAmount,Y,monthly,2024-01-01,\n"  # empty amount
        )
        resp = await client.post(
            f"/api/buckets/{bid}/subscriptions/import",
            files=_csv_file(csv_content),
        )
        body = resp.json()
        assert body["imported"] == 1
        assert len(body["failed"]) == 1
        assert body["failed"][0]["row"] == 1  # 0-indexed data rows (row 0 = first data row)

    async def test_invalid_interval_reports_row_error(
        self, client: AsyncClient
    ) -> None:
        bid = await _make_bucket(client, "ImportErr2")
        csv_content = (
            "name,provider,recurring_interval,recurring_date,amount,currency\n"
            "Bad,X,fortnightly,2024-01-01,5.0,EUR\n"
        )
        resp = await client.post(
            f"/api/buckets/{bid}/subscriptions/import",
            files=_csv_file(csv_content),
        )
        body = resp.json()
        assert body["imported"] == 0
        assert len(body["failed"]) == 1
        assert "interval" in body["failed"][0]["error"].lower()

    async def test_empty_csv_returns_zero_imported(
        self, client: AsyncClient
    ) -> None:
        bid = await _make_bucket(client, "ImportEmpty")
        csv_content = (
            "name,provider,recurring_interval,recurring_date,amount,currency\n"
        )
        resp = await client.post(
            f"/api/buckets/{bid}/subscriptions/import",
            files=_csv_file(csv_content),
        )
        body = resp.json()
        assert body["imported"] == 0
        assert body["failed"] == []

    async def test_nonexistent_bucket_returns_404(
        self, client: AsyncClient
    ) -> None:
        resp = await client.post(
            "/api/buckets/no-bucket/subscriptions/import",
            files=_csv_file(VALID_CSV),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Service-level tests for the import options (provider_fallback etc.)
# ---------------------------------------------------------------------------


class TestCsvImportOptions:
    """Tests for the keyword options added to import_subscriptions_from_csv."""

    async def _import(self, client: AsyncClient, csv_text: str, bucket_id: str):
        resp = await client.post(
            f"/api/buckets/{bucket_id}/subscriptions/import",
            files=_csv_file(csv_text),
        )
        assert resp.status_code == 200
        return resp.json()

    # provider_fallback="error" (default) ---------------------------------

    async def test_missing_provider_fails_by_default(self, client: AsyncClient):
        bid = await _make_bucket(client, "OptErr")
        csv_text = (
            "name,recurring_interval,amount,currency\n"
            "Netflix,monthly,9.99,EUR\n"
        )
        body = await self._import(client, csv_text, bid)
        assert body["imported"] == 0
        assert len(body["failed"]) == 1

    # provider_fallback="use_name" ----------------------------------------

    async def test_provider_fallback_use_name_via_service(self, client: AsyncClient):
        """Service directly: missing provider → subscription name used."""
        from backend.services.csv_import import import_subscriptions_from_csv
        from backend.database import get_db_path
        import aiosqlite

        bid = await _make_bucket(client, "OptUseName")
        csv_text = (
            "name,recurring_interval,amount,currency\n"
            "Netflix,monthly,9.99,EUR\n"
        )

        async with aiosqlite.connect(get_db_path()) as db:
            db.row_factory = aiosqlite.Row
            result = await import_subscriptions_from_csv(
                csv_text.encode(),
                bid,
                db,
                provider_fallback="use_name",
            )

        assert result["imported"] == 1
        assert result["failed"] == []

        # The subscription should exist with a provider named "Netflix"
        subs_resp = await client.get(f"/api/buckets/{bid}/subscriptions")
        sub = subs_resp.json()[0]
        assert sub["name"] == "Netflix"
        assert sub["provider_name"] == "Netflix"

    # provider_fallback="skip" --------------------------------------------

    async def test_provider_fallback_skip_via_service(self, client: AsyncClient):
        """Rows without a provider are silently skipped."""
        from backend.services.csv_import import import_subscriptions_from_csv
        from backend.database import get_db_path
        import aiosqlite

        bid = await _make_bucket(client, "OptSkip")
        csv_text = (
            "name,provider,recurring_interval,amount,currency\n"
            "Netflix,Netflix,monthly,9.99,EUR\n"
            "Unknown,,monthly,4.99,EUR\n"  # no provider → skip
        )

        async with aiosqlite.connect(get_db_path()) as db:
            db.row_factory = aiosqlite.Row
            result = await import_subscriptions_from_csv(
                csv_text.encode(),
                bid,
                db,
                provider_fallback="skip",
            )

        assert result["imported"] == 1
        assert result["failed"] == []  # skipped rows are NOT counted as failures

    # default_interval ----------------------------------------------------

    async def test_default_interval_fills_missing_column(self, client: AsyncClient):
        from backend.services.csv_import import import_subscriptions_from_csv
        from backend.database import get_db_path
        import aiosqlite

        bid = await _make_bucket(client, "OptInterval")
        csv_text = (
            "name,provider,amount,currency\n"  # no recurring_interval column
            "Spotify,Spotify,9.99,EUR\n"
        )

        async with aiosqlite.connect(get_db_path()) as db:
            db.row_factory = aiosqlite.Row
            result = await import_subscriptions_from_csv(
                csv_text.encode(),
                bid,
                db,
                provider_fallback="use_name",
                default_interval="monthly",
            )

        assert result["imported"] == 1
        subs_resp = await client.get(f"/api/buckets/{bid}/subscriptions")
        assert subs_resp.json()[0]["recurring_interval"] == "monthly"

    # default_currency ----------------------------------------------------

    async def test_default_currency_overrides_eur(self, client: AsyncClient):
        from backend.services.csv_import import import_subscriptions_from_csv
        from backend.database import get_db_path
        import aiosqlite

        bid = await _make_bucket(client, "OptCurrency")
        csv_text = (
            "name,provider,recurring_interval,amount\n"
            "Adobe,Adobe,monthly,59.99\n"
        )

        async with aiosqlite.connect(get_db_path()) as db:
            db.row_factory = aiosqlite.Row
            result = await import_subscriptions_from_csv(
                csv_text.encode(),
                bid,
                db,
                default_currency="USD",
            )

        assert result["imported"] == 1
        subs_resp = await client.get(f"/api/buckets/{bid}/subscriptions")
        assert subs_resp.json()[0]["currency"] == "USD"
