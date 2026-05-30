"""
Logo/image auto-fetch service.

Strategy
--------
1. Derive a domain name from the provider name (e.g. "Netflix" → "netflix.com").
2. Try the Clearbit Logo API: ``https://logo.clearbit.com/{domain}``
   - HTTP 200 → return that URL.
   - Any other response or connection error → fallback.
3. Fallback: return the Google Favicon service URL
   ``https://www.google.com/s2/favicons?domain={domain}&sz=128``
   (no live HTTP call needed — the browser will fetch it directly).
4. If the domain cannot be determined → return None.

The returned URL is stored in ``subscriptions.image_url``.
"""

from __future__ import annotations

import logging
import re

import httpx

logger = logging.getLogger(__name__)

_CLEARBIT_BASE = "https://logo.clearbit.com"
_GOOGLE_FAVICON_BASE = "https://www.google.com/s2/favicons"

# Characters that are not valid in a simple hostname
_NON_ALPHA = re.compile(r"[^a-z0-9-]")


def _derive_domain(provider_name: str) -> str | None:
    """
    Convert a provider display name to a best-guess domain.

    Examples
    --------
    "Netflix"     → "netflix.com"
    "Amazon Prime"→ "amazon.com"   (first word only)
    "HBO Max"     → "hbo.com"
    ""            → None
    """
    if not provider_name or not provider_name.strip():
        return None

    # Take the first word, lowercase, strip non-alphanumeric
    first_word = provider_name.strip().split()[0].lower()
    cleaned = _NON_ALPHA.sub("", first_word)
    if not cleaned:
        return None
    return f"{cleaned}.com"


async def fetch_logo_url(provider_name: str) -> str | None:
    """
    Fetch a logo URL for the given provider name.

    Returns the URL string on success, or None if no logo could be found.
    This function never raises; errors are logged and None is returned.
    """
    domain = _derive_domain(provider_name)
    if domain is None:
        return None

    clearbit_url = f"{_CLEARBIT_BASE}/{domain}"
    google_url = f"{_GOOGLE_FAVICON_BASE}?domain={domain}&sz=128"

    # --- Try Clearbit ---
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(clearbit_url)
            if resp.status_code == 200:
                logger.debug("Logo found via Clearbit for %r: %s", provider_name, clearbit_url)
                return clearbit_url
    except httpx.HTTPError as exc:
        logger.debug("Clearbit request failed for %r: %s", provider_name, exc)

    # --- Fall back to Google Favicon ---
    # We return the URL without verifying it; the browser will handle missing icons.
    logger.debug("Falling back to Google Favicon for %r: %s", provider_name, google_url)
    return google_url
