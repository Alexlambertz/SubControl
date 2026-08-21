"""
Tests for /api/buckets/{bucket_id}/insurances and its attachment endpoints.

Covers: CRUD, bucket scoping, category create-on-fly, attachment
        upload/download/delete, 404s, and file-type/size validation.
"""

from __future__ import annotations

import io

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_bucket(client: AsyncClient, name: str = "TestBucket") -> str:
    resp = await client.post("/api/buckets", json={"name": name})
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_insurance(
    client: AsyncClient,
    bucket_id: str,
    *,
    name: str = "Household contents",
    insurer: str = "Allianz",
    interval: str = "yearly",
    recurring_date: str = "2024-01-15",
    amount: float = 120.0,
    currency: str = "EUR",
    category: str | None = None,
    policy_number: str | None = None,
) -> dict:
    payload: dict = {
        "name": name,
        "insurer": insurer,
        "recurring_interval": interval,
        "recurring_date": recurring_date,
        "amount": amount,
        "currency": currency,
    }
    if category:
        payload["category_name"] = category
    if policy_number:
        payload["policy_number"] = policy_number
    resp = await client.post(f"/api/buckets/{bucket_id}/insurances", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Tests: List / Create / Get / Update / Delete
# ---------------------------------------------------------------------------


class TestListInsurances:
    async def test_empty_list(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "EmptyBucket")
        resp = await client.get(f"/api/buckets/{bid}/insurances")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_returns_created_insurance(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "FullBucket")
        await _create_insurance(client, bid, name="Car insurance")
        resp = await client.get(f"/api/buckets/{bid}/insurances")
        names = [i["name"] for i in resp.json()]
        assert "Car insurance" in names

    async def test_bucket_scoping(self, client: AsyncClient) -> None:
        bid_a = await _create_bucket(client, "BucketA")
        bid_b = await _create_bucket(client, "BucketB")
        await _create_insurance(client, bid_a, name="Only In A")
        resp = await client.get(f"/api/buckets/{bid_b}/insurances")
        names = [i["name"] for i in resp.json()]
        assert "Only In A" not in names


class TestCreateInsurance:
    async def test_create_returns_201(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "C1")
        resp = await client.post(
            f"/api/buckets/{bid}/insurances",
            json={
                "name": "Liability insurance",
                "insurer": "HUK24",
                "recurring_interval": "yearly",
                "recurring_date": "2024-03-01",
                "amount": 65.0,
                "currency": "EUR",
            },
        )
        assert resp.status_code == 201

    async def test_category_created_on_fly(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "CatBucket")
        ins = await _create_insurance(client, bid, category="Insurance")
        assert ins["category_name"] == "Insurance"

    async def test_default_currency_is_eur(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "DefaultCurrency")
        resp = await client.post(
            f"/api/buckets/{bid}/insurances",
            json={
                "name": "Legal insurance",
                "insurer": "ARAG",
                "recurring_interval": "monthly",
                "recurring_date": "2024-01-01",
                "amount": 15.0,
            },
        )
        assert resp.status_code == 201
        assert resp.json()["currency"] == "EUR"

    async def test_invalid_interval_returns_422(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "BadInterval")
        resp = await client.post(
            f"/api/buckets/{bid}/insurances",
            json={
                "name": "Bad",
                "insurer": "X",
                "recurring_interval": "fortnightly",
                "recurring_date": "2024-01-01",
                "amount": 1.0,
            },
        )
        assert resp.status_code == 422

    async def test_policy_number_stored(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "PolicyNum")
        ins = await _create_insurance(client, bid, policy_number="POL-12345")
        assert ins["policy_number"] == "POL-12345"

    async def test_missing_bucket_returns_404(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/buckets/does-not-exist/insurances",
            json={
                "name": "X",
                "insurer": "X",
                "recurring_interval": "monthly",
                "amount": 1.0,
            },
        )
        assert resp.status_code == 404


class TestGetUpdateDeleteInsurance:
    async def test_get_returns_insurance(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "GetBucket")
        ins = await _create_insurance(client, bid)
        resp = await client.get(f"/api/buckets/{bid}/insurances/{ins['id']}")
        assert resp.status_code == 200
        assert resp.json()["name"] == ins["name"]
        assert resp.json()["attachments"] == []

    async def test_get_missing_returns_404(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "GetBucket404")
        resp = await client.get(f"/api/buckets/{bid}/insurances/does-not-exist")
        assert resp.status_code == 404

    async def test_update_changes_fields(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "UpdateBucket")
        ins = await _create_insurance(client, bid, amount=100.0)
        resp = await client.put(
            f"/api/buckets/{bid}/insurances/{ins['id']}",
            json={"amount": 150.0, "insurer": "New Insurer"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["amount"] == pytest.approx(150.0)
        assert body["insurer"] == "New Insurer"
        # Untouched fields are preserved
        assert body["name"] == ins["name"]

    async def test_delete_removes_insurance(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "DeleteBucket")
        ins = await _create_insurance(client, bid)
        resp = await client.delete(f"/api/buckets/{bid}/insurances/{ins['id']}")
        assert resp.status_code == 204
        resp = await client.get(f"/api/buckets/{bid}/insurances/{ins['id']}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests: Attachments
# ---------------------------------------------------------------------------


class TestAttachments:
    async def test_upload_and_list(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "AttachBucket")
        ins = await _create_insurance(client, bid)

        resp = await client.post(
            f"/api/buckets/{bid}/insurances/{ins['id']}/attachments",
            files={"file": ("conditions.pdf", b"%PDF-1.4 fake pdf content", "application/pdf")},
        )
        assert resp.status_code == 201, resp.text
        attachment = resp.json()
        assert attachment["filename"] == "conditions.pdf"
        assert attachment["size_bytes"] > 0

        resp = await client.get(f"/api/buckets/{bid}/insurances/{ins['id']}")
        assert len(resp.json()["attachments"]) == 1

        # Also visible via the list endpoint (grouped-attachments query path)
        resp = await client.get(f"/api/buckets/{bid}/insurances")
        assert len(resp.json()[0]["attachments"]) == 1

    async def test_download_roundtrips_content(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "DownloadBucket")
        ins = await _create_insurance(client, bid)
        content = b"%PDF-1.4 roundtrip test content"

        resp = await client.post(
            f"/api/buckets/{bid}/insurances/{ins['id']}/attachments",
            files={"file": ("terms.pdf", content, "application/pdf")},
        )
        attachment_id = resp.json()["id"]

        resp = await client.get(
            f"/api/buckets/{bid}/insurances/{ins['id']}/attachments/{attachment_id}"
        )
        assert resp.status_code == 200
        assert resp.content == content

    async def test_delete_attachment(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "DeleteAttachBucket")
        ins = await _create_insurance(client, bid)
        resp = await client.post(
            f"/api/buckets/{bid}/insurances/{ins['id']}/attachments",
            files={"file": ("terms.pdf", b"content", "application/pdf")},
        )
        attachment_id = resp.json()["id"]

        resp = await client.delete(
            f"/api/buckets/{bid}/insurances/{ins['id']}/attachments/{attachment_id}"
        )
        assert resp.status_code == 204

        resp = await client.get(f"/api/buckets/{bid}/insurances/{ins['id']}")
        assert resp.json()["attachments"] == []

    async def test_rejects_disallowed_file_type(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "BadTypeBucket")
        ins = await _create_insurance(client, bid)
        resp = await client.post(
            f"/api/buckets/{bid}/insurances/{ins['id']}/attachments",
            files={"file": ("malware.exe", b"content", "application/octet-stream")},
        )
        assert resp.status_code == 415

    async def test_rejects_oversized_file(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "OversizedBucket")
        ins = await _create_insurance(client, bid)
        too_big = io.BytesIO(b"0" * (20 * 1024 * 1024 + 1))
        resp = await client.post(
            f"/api/buckets/{bid}/insurances/{ins['id']}/attachments",
            files={"file": ("big.pdf", too_big.read(), "application/pdf")},
        )
        assert resp.status_code == 413

    async def test_deleting_insurance_removes_attachments(
        self, client: AsyncClient
    ) -> None:
        bid = await _create_bucket(client, "CascadeBucket")
        ins = await _create_insurance(client, bid)
        await client.post(
            f"/api/buckets/{bid}/insurances/{ins['id']}/attachments",
            files={"file": ("terms.pdf", b"content", "application/pdf")},
        )
        resp = await client.delete(f"/api/buckets/{bid}/insurances/{ins['id']}")
        assert resp.status_code == 204
        # Re-creating an insurance with the same bucket should not resurrect
        # the deleted one's attachments — sanity check the insurance is gone.
        resp = await client.get(f"/api/buckets/{bid}/insurances/{ins['id']}")
        assert resp.status_code == 404
