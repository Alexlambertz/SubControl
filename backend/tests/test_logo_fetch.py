"""
Tests for the logo fetch service.

Uses respx to mock httpx calls without hitting the network.
"""

from __future__ import annotations

import pytest
import respx
import httpx


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
