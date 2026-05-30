"""
Thin HTTP client that calls the SubControl REST API on behalf of MCP tools.

Configuration (environment variables)
--------------------------------------
SUBCONTROL_API_URL   Base URL of the running SubControl backend (default: http://localhost:8000)
SUBCONTROL_API_KEY   Optional API key sent as an ``X-API-Key`` header
"""

from __future__ import annotations

import os
from typing import Any

import httpx

_BASE_URL = os.environ.get("SUBCONTROL_API_URL", "http://localhost:8000").rstrip("/")
_API_KEY = os.environ.get("SUBCONTROL_API_KEY", "")


def _headers() -> dict[str, str]:
    h: dict[str, str] = {"Content-Type": "application/json"}
    if _API_KEY:
        h["X-API-Key"] = _API_KEY
    return h


async def api_get(path: str, params: dict | None = None) -> Any:
    """Perform a GET request to the SubControl API."""
    async with httpx.AsyncClient(base_url=_BASE_URL, headers=_headers()) as client:
        resp = await client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()


async def api_post(path: str, body: dict) -> Any:
    """Perform a POST request to the SubControl API."""
    async with httpx.AsyncClient(base_url=_BASE_URL, headers=_headers()) as client:
        resp = await client.post(path, json=body)
        resp.raise_for_status()
        return resp.json()


async def api_put(path: str, body: dict) -> Any:
    """Perform a PUT request to the SubControl API."""
    async with httpx.AsyncClient(base_url=_BASE_URL, headers=_headers()) as client:
        resp = await client.put(path, json=body)
        resp.raise_for_status()
        return resp.json()


async def api_delete(path: str) -> Any:
    """Perform a DELETE request to the SubControl API."""
    async with httpx.AsyncClient(base_url=_BASE_URL, headers=_headers()) as client:
        resp = await client.delete(path)
        resp.raise_for_status()
        if resp.status_code == 204:
            return {"deleted": True}
        return resp.json()
