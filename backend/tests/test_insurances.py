"""
Tests for /api/buckets/{bucket_id}/insurances and its attachment endpoints.

Covers: CRUD, bucket scoping, category create-on-fly, attachment
        upload/download/delete, 404s, and file-type/size validation.
"""

from __future__ import annotations

import csv
import io

import aiosqlite
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

    async def test_explicit_null_clears_end_date(self, client: AsyncClient) -> None:
        """Regression: an explicit null must clear end_date, not be ignored."""
        bid = await _create_bucket(client, "ClearEndDate")
        ins = await _create_insurance(client, bid)
        set_resp = await client.put(
            f"/api/buckets/{bid}/insurances/{ins['id']}",
            json={"end_date": "2026-12-31"},
        )
        assert set_resp.json()["end_date"] == "2026-12-31"

        clear_resp = await client.put(
            f"/api/buckets/{bid}/insurances/{ins['id']}",
            json={"end_date": None},
        )
        assert clear_resp.status_code == 200
        assert clear_resp.json()["end_date"] is None

    async def test_omitted_end_date_is_preserved(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "PreserveEndDate")
        ins = await _create_insurance(client, bid)
        await client.put(
            f"/api/buckets/{bid}/insurances/{ins['id']}",
            json={"end_date": "2026-12-31"},
        )
        resp = await client.put(
            f"/api/buckets/{bid}/insurances/{ins['id']}",
            json={"amount": 42.0},
        )
        assert resp.status_code == 200
        assert resp.json()["end_date"] == "2026-12-31"
        assert resp.json()["amount"] == pytest.approx(42.0)

    async def test_explicit_null_clears_category(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "ClearCategory")
        ins = await _create_insurance(client, bid, category="Insurance")
        assert ins["category_name"] == "Insurance"

        resp = await client.put(
            f"/api/buckets/{bid}/insurances/{ins['id']}",
            json={"category_name": None},
        )
        assert resp.status_code == 200
        assert resp.json()["category_name"] is None

    async def test_explicit_null_clears_policy_number_and_notes(
        self, client: AsyncClient
    ) -> None:
        bid = await _create_bucket(client, "ClearTextFields")
        ins = await _create_insurance(client, bid, policy_number="POL-1")
        await client.put(
            f"/api/buckets/{bid}/insurances/{ins['id']}",
            json={"notes": "some notes"},
        )
        resp = await client.put(
            f"/api/buckets/{bid}/insurances/{ins['id']}",
            json={"policy_number": None, "notes": None},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["policy_number"] is None
        assert body["notes"] is None


class TestInsuranceHistory:
    async def test_update_records_history(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "HistoryBucket")
        ins = await _create_insurance(client, bid, amount=100.0)
        resp = await client.put(
            f"/api/buckets/{bid}/insurances/{ins['id']}",
            json={"amount": 150.0, "insurer": "New Insurer"},
        )
        assert resp.status_code == 200

        hist_resp = await client.get(
            f"/api/buckets/{bid}/insurances/{ins['id']}/history"
        )
        assert hist_resp.status_code == 200
        entries = {e["field"]: e for e in hist_resp.json()}
        assert set(entries) == {"amount", "insurer"}
        assert entries["amount"]["old_value"] == "100.0"
        assert entries["amount"]["new_value"] == "150.0"
        assert entries["insurer"]["old_value"] == "Allianz"
        assert entries["insurer"]["new_value"] == "New Insurer"
        assert entries["amount"]["changed_by_username"] == "dev_admin"

    async def test_partial_update_records_only_changed_fields(
        self, client: AsyncClient
    ) -> None:
        bid = await _create_bucket(client, "PartialHistoryBucket")
        ins = await _create_insurance(client, bid, amount=100.0)
        resp = await client.put(
            f"/api/buckets/{bid}/insurances/{ins['id']}",
            json={"notes": "renewed early"},
        )
        assert resp.status_code == 200

        hist_resp = await client.get(
            f"/api/buckets/{bid}/insurances/{ins['id']}/history"
        )
        entries = hist_resp.json()
        assert len(entries) == 1
        assert entries[0]["field"] == "notes"

    async def test_create_does_not_record_history(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "NoHistoryOnCreate")
        ins = await _create_insurance(client, bid)

        hist_resp = await client.get(
            f"/api/buckets/{bid}/insurances/{ins['id']}/history"
        )
        assert hist_resp.json() == []

    async def test_history_not_found_for_missing_insurance(
        self, client: AsyncClient
    ) -> None:
        bid = await _create_bucket(client, "MissingInsuranceHistory")
        resp = await client.get(f"/api/buckets/{bid}/insurances/no-id/history")
        assert resp.status_code == 404

    async def test_delete_cascades_history(
        self, client: AsyncClient, db: aiosqlite.Connection
    ) -> None:
        bid = await _create_bucket(client, "CascadeHistoryBucket")
        ins = await _create_insurance(client, bid, amount=100.0)
        await client.put(
            f"/api/buckets/{bid}/insurances/{ins['id']}",
            json={"amount": 150.0},
        )
        del_resp = await client.delete(f"/api/buckets/{bid}/insurances/{ins['id']}")
        assert del_resp.status_code == 204

        async with db.execute(
            "SELECT COUNT(*) AS n FROM insurance_history WHERE insurance_id = ?",
            (ins["id"],),
        ) as cur:
            row = await cur.fetchone()
        assert row["n"] == 0


class TestBulkUpdateInsurances:
    async def test_bulk_update_applies_field_to_all(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "BulkInsBucket")
        ins1 = await _create_insurance(client, bid, name="Ins1", amount=5.0)
        ins2 = await _create_insurance(client, bid, name="Ins2", amount=7.0)

        resp = await client.patch(
            f"/api/buckets/{bid}/insurances/bulk",
            json={"ids": [ins1["id"], ins2["id"]], "update": {"amount": 19.99}},
        )
        assert resp.status_code == 200
        assert resp.json()["updated"] == 2

        for ins_id in (ins1["id"], ins2["id"]):
            get_resp = await client.get(f"/api/buckets/{bid}/insurances/{ins_id}")
            assert get_resp.json()["amount"] == pytest.approx(19.99)

    async def test_bulk_update_only_touches_specified_fields(
        self, client: AsyncClient
    ) -> None:
        bid = await _create_bucket(client, "BulkInsPartialBucket")
        ins = await _create_insurance(client, bid, name="Untouched", amount=5.0)

        resp = await client.patch(
            f"/api/buckets/{bid}/insurances/bulk",
            json={"ids": [ins["id"]], "update": {"amount": 42.0}},
        )
        assert resp.status_code == 200

        get_resp = await client.get(f"/api/buckets/{bid}/insurances/{ins['id']}")
        body = get_resp.json()
        assert body["amount"] == pytest.approx(42.0)
        assert body["name"] == "Untouched"

    async def test_bulk_update_explicit_null_clears_field(
        self, client: AsyncClient
    ) -> None:
        bid = await _create_bucket(client, "BulkInsClearBucket")
        ins = await _create_insurance(client, bid, policy_number="POL-1")
        assert ins["policy_number"] == "POL-1"

        resp = await client.patch(
            f"/api/buckets/{bid}/insurances/bulk",
            json={"ids": [ins["id"]], "update": {"policy_number": None}},
        )
        assert resp.status_code == 200

        get_resp = await client.get(f"/api/buckets/{bid}/insurances/{ins['id']}")
        assert get_resp.json()["policy_number"] is None

    async def test_bulk_update_records_history_per_record(
        self, client: AsyncClient
    ) -> None:
        bid = await _create_bucket(client, "BulkInsHistoryBucket")
        ins1 = await _create_insurance(client, bid, name="A", amount=5.0)
        ins2 = await _create_insurance(client, bid, name="B", amount=5.0)

        await client.patch(
            f"/api/buckets/{bid}/insurances/bulk",
            json={"ids": [ins1["id"], ins2["id"]], "update": {"amount": 9.0}},
        )

        for ins_id in (ins1["id"], ins2["id"]):
            hist_resp = await client.get(
                f"/api/buckets/{bid}/insurances/{ins_id}/history"
            )
            entries = hist_resp.json()
            assert len(entries) == 1
            assert entries[0]["field"] == "amount"
            assert entries[0]["old_value"] == "5.0"
            assert entries[0]["new_value"] == "9.0"

    async def test_bulk_update_owner_name(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "BulkInsOwnerBucket")
        ins = await _create_insurance(client, bid)

        resp = await client.patch(
            f"/api/buckets/{bid}/insurances/bulk",
            json={"ids": [ins["id"]], "update": {"owner_name": "Alex"}},
        )
        assert resp.status_code == 200

        get_resp = await client.get(f"/api/buckets/{bid}/insurances/{ins['id']}")
        assert get_resp.json()["owner_name"] == "Alex"

    async def test_bulk_update_rejects_id_from_another_bucket(
        self, client: AsyncClient
    ) -> None:
        bid1 = await _create_bucket(client, "BulkInsCrossA")
        bid2 = await _create_bucket(client, "BulkInsCrossB")
        ins_in_other_bucket = await _create_insurance(client, bid2, amount=5.0)

        resp = await client.patch(
            f"/api/buckets/{bid1}/insurances/bulk",
            json={"ids": [ins_in_other_bucket["id"]], "update": {"amount": 99.0}},
        )
        assert resp.status_code == 404

        get_resp = await client.get(
            f"/api/buckets/{bid2}/insurances/{ins_in_other_bucket['id']}"
        )
        assert get_resp.json()["amount"] == pytest.approx(5.0)


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
        body = resp.json()
        assert body["suggested_updates"] == {}
        attachment = body["attachment"]
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
        attachment_id = resp.json()["attachment"]["id"]

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
        attachment_id = resp.json()["attachment"]["id"]

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


# ---------------------------------------------------------------------------
# Tests: CSV export
# ---------------------------------------------------------------------------


class TestExportInsurances:
    async def test_export_returns_csv(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "ExportBucket1")
        await _create_insurance(
            client,
            bid,
            name="Household contents",
            insurer="Allianz",
            category="Insurance",
            policy_number="POL-1",
        )
        resp = await client.get(f"/api/buckets/{bid}/insurances/export")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert "attachment; filename=" in resp.headers["content-disposition"]

        rows = list(csv.DictReader(io.StringIO(resp.text)))
        assert len(rows) == 1
        row = rows[0]
        assert row["name"] == "Household contents"
        assert row["insurer"] == "Allianz"
        assert row["policy_number"] == "POL-1"
        assert row["category"] == "Insurance"
        assert row["recurring_interval"] == "yearly"
        assert row["amount"] == "120.0"
        assert row["currency"] == "EUR"

    async def test_export_not_shadowed_by_insurance_id_route(
        self, client: AsyncClient
    ) -> None:
        # Regression test: /insurances/export must be matched by the export
        # route, not by GET /{insurance_id} treating "export" as an id.
        bid = await _create_bucket(client, "ExportBucket2")
        resp = await client.get(f"/api/buckets/{bid}/insurances/export")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")

    async def test_export_empty_bucket_returns_header_only(
        self, client: AsyncClient
    ) -> None:
        bid = await _create_bucket(client, "ExportBucket3")
        resp = await client.get(f"/api/buckets/{bid}/insurances/export")
        assert resp.status_code == 200
        rows = list(csv.DictReader(io.StringIO(resp.text)))
        assert rows == []

    async def test_export_scoped_to_bucket(self, client: AsyncClient) -> None:
        bid_a = await _create_bucket(client, "ExportBucketA")
        bid_b = await _create_bucket(client, "ExportBucketB")
        await _create_insurance(client, bid_a, name="Only In A")
        resp = await client.get(f"/api/buckets/{bid_b}/insurances/export")
        assert resp.status_code == 200
        rows = list(csv.DictReader(io.StringIO(resp.text)))
        names = [r["name"] for r in rows]
        assert "Only In A" not in names

    async def test_export_missing_bucket_returns_404(
        self, client: AsyncClient
    ) -> None:
        resp = await client.get("/api/buckets/does-not-exist/insurances/export")
        assert resp.status_code == 404
