"""
Tests for cache headers on the built-SPA static file serving in main.py.

The app can be installed as a PWA (home-screen standalone app), and mobile
browser engines are notoriously sticky about caching the root document —
these tests guard against a regression that would leave installed PWAs
stuck on a stale shell after a deploy.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from httpx import AsyncClient

STATIC_DIR = Path(__file__).parent.parent / "static"


@pytest.fixture()
def built_frontend():
    """
    Create a minimal fake frontend build under backend/static/ so
    create_app() mounts the SPA static-serving routes — mirroring what the
    Docker build does by copying frontend/dist/ into place. Backs up and
    restores any pre-existing local build instead of destroying it.
    """
    backed_up = None
    if STATIC_DIR.exists():
        backed_up = STATIC_DIR.with_name("static.bak-test")
        STATIC_DIR.rename(backed_up)

    STATIC_DIR.mkdir()
    (STATIC_DIR / "index.html").write_text("<html><body>SubControl</body></html>")
    (STATIC_DIR / "manifest.json").write_text('{"name": "SubControl"}')
    assets_dir = STATIC_DIR / "assets"
    assets_dir.mkdir()
    (assets_dir / "index-abc123.js").write_text("console.log('x')")

    try:
        yield
    finally:
        shutil.rmtree(STATIC_DIR)
        if backed_up is not None:
            backed_up.rename(STATIC_DIR)


class TestStaticCacheHeaders:
    async def test_index_html_is_never_cached(
        self, built_frontend, client: AsyncClient
    ) -> None:
        resp = await client.get("/")
        assert resp.status_code == 200
        assert resp.headers["cache-control"] == "no-store, no-cache, must-revalidate"
        assert resp.headers["pragma"] == "no-cache"
        assert resp.headers["expires"] == "0"

    async def test_spa_fallback_route_is_never_cached(
        self, built_frontend, client: AsyncClient
    ) -> None:
        """Unknown client-side routes (e.g. /buckets/xyz) fall back to
        index.html and must carry the same no-cache headers."""
        resp = await client.get("/buckets/some-deep-route")
        assert resp.status_code == 200
        assert resp.headers["cache-control"] == "no-store, no-cache, must-revalidate"

    async def test_manifest_is_never_cached(
        self, built_frontend, client: AsyncClient
    ) -> None:
        resp = await client.get("/manifest.json")
        assert resp.status_code == 200
        assert resp.headers["cache-control"] == "no-store, no-cache, must-revalidate"

    async def test_hashed_asset_is_cached_immutably(
        self, built_frontend, client: AsyncClient
    ) -> None:
        """Content-hashed bundle filenames are safe to cache forever — a
        new deploy produces a new filename, never a stale one at the same URL."""
        resp = await client.get("/assets/index-abc123.js")
        assert resp.status_code == 200
        assert resp.headers["cache-control"] == "public, max-age=31536000, immutable"
