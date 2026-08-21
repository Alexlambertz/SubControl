"""
Tests for /api/buckets/{bucket_id}/subscriptions/{sub_id}/attachments.

Mirrors backend/tests/test_insurances.py's TestAttachments class — same
storage/validation logic, reused for subscriptions.
"""

from __future__ import annotations

import io

import pytest
from httpx import AsyncClient


async def _create_bucket(client: AsyncClient, name: str = "TestBucket") -> str:
    resp = await client.post("/api/buckets", json={"name": name})
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_sub(
    client: AsyncClient,
    bucket_id: str,
    *,
    name: str = "Netflix",
    provider: str = "Netflix",
    interval: str = "monthly",
    recurring_date: str = "2024-01-15",
    amount: float = 9.99,
) -> dict:
    resp = await client.post(
        f"/api/buckets/{bucket_id}/subscriptions",
        json={
            "name": name,
            "provider_name": provider,
            "recurring_interval": interval,
            "recurring_date": recurring_date,
            "amount": amount,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestSubscriptionAttachments:
    async def test_upload_and_list(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "AttachBucket")
        sub = await _create_sub(client, bid)

        resp = await client.post(
            f"/api/buckets/{bid}/subscriptions/{sub['id']}/attachments",
            files={"file": ("invoice.pdf", b"%PDF-1.4 fake pdf content", "application/pdf")},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["suggested_updates"] == {}
        attachment = body["attachment"]
        assert attachment["filename"] == "invoice.pdf"
        assert attachment["size_bytes"] > 0

        resp = await client.get(f"/api/buckets/{bid}/subscriptions/{sub['id']}")
        assert len(resp.json()["attachments"]) == 1

        # Also visible via the list endpoint (grouped-attachments query path)
        resp = await client.get(f"/api/buckets/{bid}/subscriptions")
        subs_by_id = {s["id"]: s for s in resp.json()}
        assert len(subs_by_id[sub["id"]]["attachments"]) == 1

    async def test_download_roundtrips_content(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "DownloadBucket")
        sub = await _create_sub(client, bid)
        content = b"%PDF-1.4 roundtrip test content"

        resp = await client.post(
            f"/api/buckets/{bid}/subscriptions/{sub['id']}/attachments",
            files={"file": ("invoice.pdf", content, "application/pdf")},
        )
        attachment_id = resp.json()["attachment"]["id"]

        resp = await client.get(
            f"/api/buckets/{bid}/subscriptions/{sub['id']}/attachments/{attachment_id}"
        )
        assert resp.status_code == 200
        assert resp.content == content

    async def test_delete_attachment(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "DeleteAttachBucket")
        sub = await _create_sub(client, bid)
        resp = await client.post(
            f"/api/buckets/{bid}/subscriptions/{sub['id']}/attachments",
            files={"file": ("invoice.pdf", b"content", "application/pdf")},
        )
        attachment_id = resp.json()["attachment"]["id"]

        resp = await client.delete(
            f"/api/buckets/{bid}/subscriptions/{sub['id']}/attachments/{attachment_id}"
        )
        assert resp.status_code == 204

        resp = await client.get(f"/api/buckets/{bid}/subscriptions/{sub['id']}")
        assert resp.json()["attachments"] == []

    async def test_rejects_disallowed_file_type(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "BadTypeBucket")
        sub = await _create_sub(client, bid)
        resp = await client.post(
            f"/api/buckets/{bid}/subscriptions/{sub['id']}/attachments",
            files={"file": ("malware.exe", b"content", "application/octet-stream")},
        )
        assert resp.status_code == 415

    async def test_rejects_oversized_file(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "OversizedBucket")
        sub = await _create_sub(client, bid)
        too_big = io.BytesIO(b"0" * (20 * 1024 * 1024 + 1))
        resp = await client.post(
            f"/api/buckets/{bid}/subscriptions/{sub['id']}/attachments",
            files={"file": ("big.pdf", too_big.read(), "application/pdf")},
        )
        assert resp.status_code == 413

    async def test_deleting_subscription_removes_attachments(
        self, client: AsyncClient
    ) -> None:
        bid = await _create_bucket(client, "CascadeBucket")
        sub = await _create_sub(client, bid)
        await client.post(
            f"/api/buckets/{bid}/subscriptions/{sub['id']}/attachments",
            files={"file": ("invoice.pdf", b"content", "application/pdf")},
        )
        resp = await client.delete(f"/api/buckets/{bid}/subscriptions/{sub['id']}")
        assert resp.status_code == 204
        resp = await client.get(f"/api/buckets/{bid}/subscriptions/{sub['id']}")
        assert resp.status_code == 404

    async def test_attachment_not_found_returns_404(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "NotFoundBucket")
        sub = await _create_sub(client, bid)
        resp = await client.get(
            f"/api/buckets/{bid}/subscriptions/{sub['id']}/attachments/does-not-exist"
        )
        assert resp.status_code == 404
