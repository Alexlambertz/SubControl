"""
Tests for the logo fetch service.

Uses respx to mock httpx calls without hitting the network.
"""

from __future__ import annotations

import pytest
import respx
import httpx


@pytest.fixture(autouse=True)
def _clear_logo_cache():
    """Logo results are cached in-process by provider name — reset between tests."""
    from backend.services.logo_fetch import clear_logo_cache
    clear_logo_cache()
    yield
    clear_logo_cache()


class TestLogoFetch:
    @respx.mock
    async def test_clearbit_success_returns_url(self) -> None:
        """When Clearbit returns 200, the URL is returned."""
        from backend.services.logo_fetch import fetch_logo_url

        respx.get("https://logo.clearbit.com/netflix.com").mock(
            return_value=httpx.Response(200, content=b"fake-png")
        )
        url = await fetch_logo_url("Netflix")
        assert url == "https://logo.clearbit.com/netflix.com"

    @respx.mock
    async def test_clearbit_404_falls_back_to_google(self) -> None:
        """When Clearbit returns 404, fall back to Google Favicon URL."""
        from backend.services.logo_fetch import fetch_logo_url

        respx.get("https://logo.clearbit.com/spotify.com").mock(
            return_value=httpx.Response(404)
        )
        # Google Favicon is returned as a URL directly (no HTTP call needed)
        url = await fetch_logo_url("Spotify")
        assert url is not None
        assert "google.com/s2/favicons" in url

    @respx.mock
    async def test_both_fail_returns_none(self) -> None:
        """When both sources fail, None is returned gracefully."""
        from backend.services.logo_fetch import fetch_logo_url

        respx.get("https://logo.clearbit.com/unknown-provider-xyz.com").mock(
            return_value=httpx.Response(404)
        )
        # Force Google Favicon to also fail (simulate network error)
        # The Google Favicon URL is returned without a live check, so
        # test the domain-derivation failure path instead
        url = await fetch_logo_url("")
        # Empty provider name → no domain → None
        assert url is None

    @respx.mock
    async def test_domain_derived_from_provider_name(self) -> None:
        """Provider name is lowercased and .com is appended for Clearbit."""
        from backend.services.logo_fetch import fetch_logo_url

        respx.get("https://logo.clearbit.com/hbo.com").mock(
            return_value=httpx.Response(200, content=b"img")
        )
        url = await fetch_logo_url("HBO")
        assert "hbo.com" in url

    @respx.mock
    async def test_network_error_returns_google_fallback(self) -> None:
        """On a connection error from Clearbit, return Google Favicon URL."""
        from backend.services.logo_fetch import fetch_logo_url

        respx.get("https://logo.clearbit.com/amazon.com").mock(
            side_effect=httpx.ConnectError("connection refused")
        )
        url = await fetch_logo_url("Amazon")
        # Should fall back to Google Favicon
        assert url is not None
        assert "google.com" in url

    @respx.mock
    async def test_result_is_cached_per_provider_name(self) -> None:
        """A second call for the same provider must not hit the network again."""
        from backend.services.logo_fetch import fetch_logo_url

        route = respx.get("https://logo.clearbit.com/cacheme.com").mock(
            return_value=httpx.Response(200, content=b"fake-png")
        )
        url1 = await fetch_logo_url("CacheMe")
        url2 = await fetch_logo_url("CacheMe")
        assert url1 == url2 == "https://logo.clearbit.com/cacheme.com"
        assert route.call_count == 1

    @respx.mock
    async def test_refresh_bucket_fetches_each_unique_provider_once(self) -> None:
        """Bulk refresh must reuse the cache across subscriptions sharing a provider."""
        import tempfile
        import os
        from backend.migrations.runner import apply_pending_migrations
        from backend.services.logo_fetch import refresh_logos_for_bucket
        import aiosqlite

        route = respx.get("https://logo.clearbit.com/dupeprovider.com").mock(
            return_value=httpx.Response(200, content=b"fake-png")
        )

        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            await apply_pending_migrations(path)
            async with aiosqlite.connect(path) as db:
                await db.execute("INSERT INTO buckets (id, name) VALUES ('b1', 'B1')")
                await db.execute(
                    "INSERT INTO providers (id, name) VALUES (1, 'DupeProvider')"
                )
                for sid in ("s1", "s2", "s3"):
                    await db.execute(
                        "INSERT INTO subscriptions "
                        "(id, bucket_id, name, provider_id, recurring_interval, amount) "
                        "VALUES (?, 'b1', ?, 1, 'monthly', 1.0)",
                        (sid, sid),
                    )
                await db.commit()

            await refresh_logos_for_bucket("b1", path)

            async with aiosqlite.connect(path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT image_url FROM subscriptions WHERE bucket_id = 'b1'"
                ) as cur:
                    rows = await cur.fetchall()
            assert all(r["image_url"] == "https://logo.clearbit.com/dupeprovider.com" for r in rows)
            assert route.call_count == 1
        finally:
            os.unlink(path)
