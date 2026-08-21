"""
Tests for AI-assisted insurance discovery and document import:
- POST /api/buckets/{bucket_id}/insurances/detect-candidates
- POST /api/buckets/{bucket_id}/subscriptions/{sub_id}/migrate-to-insurance
- POST /api/buckets/{bucket_id}/ai-import/extract

We mock the openai.AsyncOpenAI client to avoid real network calls, following
the same pattern as test_chat.py.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Mock helpers — non-streaming chat.completions.create response shape
# ---------------------------------------------------------------------------


class _MockMessage:
    def __init__(self, content: str | None):
        self.content = content


class _MockChoice:
    def __init__(self, content: str | None):
        self.message = _MockMessage(content)


class _MockResponse:
    def __init__(self, content: str | None):
        self.choices = [_MockChoice(content)]


def _mock_client(json_content: dict) -> MagicMock:
    """An AsyncOpenAI-shaped mock whose create() returns a fixed JSON body."""
    instance = MagicMock()
    instance.chat.completions.create = AsyncMock(
        return_value=_MockResponse(json.dumps(json_content))
    )
    return instance


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_bucket(client: AsyncClient, name: str = "TestBucket") -> str:
    resp = await client.post("/api/buckets", json={"name": name})
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_sub(
    client: AsyncClient,
    bucket_id: str,
    *,
    name: str = "HUK24 Hausrat",
    provider: str = "HUK24",
    interval: str = "yearly",
    recurring_date: str = "2024-01-15",
    amount: float = 120.0,
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


async def _configure_ai(client: AsyncClient) -> None:
    await client.put("/api/settings/ai_api_url", json={"value": "https://api.openai.com/v1"})
    await client.put("/api/settings/ai_api_key", json={"value": "test-key"})
    await client.put("/api/settings/ai_model", json={"value": "gpt-4o-mini"})


class _NoAiConfig:
    """
    Context manager blanking both the DB setting and the env-var fallback
    (the real dev .env has a live OpenRouter key configured — see
    test_chat.py's identical pattern) so "AI not configured" is reachable.
    """

    def __init__(self, client: AsyncClient) -> None:
        self.client = client
        self._original_url = ""

    async def __aenter__(self) -> "_NoAiConfig":
        import backend.config as cfg
        self._original_url = cfg.settings.ai_api_url
        cfg.settings.ai_api_url = ""
        await self.client.put("/api/settings/ai_api_url", json={"value": ""})
        return self

    async def __aexit__(self, *exc: object) -> None:
        import backend.config as cfg
        cfg.settings.ai_api_url = self._original_url


# ---------------------------------------------------------------------------
# detect-candidates
# ---------------------------------------------------------------------------


class TestDetectCandidates:
    async def test_not_configured_returns_400(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client)
        async with _NoAiConfig(client):
            resp = await client.post(f"/api/buckets/{bid}/insurances/detect-candidates")
        assert resp.status_code == 400

    async def test_returns_candidates_for_matching_subscription(
        self, client: AsyncClient
    ) -> None:
        bid = await _create_bucket(client)
        sub = await _create_sub(client, bid, name="HUK24 Hausrat", provider="HUK24")
        await _create_sub(client, bid, name="Netflix", provider="Netflix", amount=9.99)
        await _configure_ai(client)

        mock_instance = _mock_client(
            {
                "candidates": [
                    {
                        "subscription_id": sub["id"],
                        "insurer": "HUK24",
                        "category_name": "Insurance",
                        "confidence": "high",
                        "reason": "Well-known German insurer",
                    }
                ]
            }
        )

        with patch("backend.services.ai_extract.AsyncOpenAI", return_value=mock_instance):
            resp = await client.post(f"/api/buckets/{bid}/insurances/detect-candidates")

        assert resp.status_code == 200
        candidates = resp.json()["candidates"]
        assert len(candidates) == 1
        assert candidates[0]["subscription_id"] == sub["id"]
        assert candidates[0]["suggested_insurer"] == "HUK24"
        assert candidates[0]["confidence"] == "high"

    async def test_hallucinated_subscription_id_is_dropped(
        self, client: AsyncClient
    ) -> None:
        bid = await _create_bucket(client)
        await _create_sub(client, bid)
        await _configure_ai(client)

        mock_instance = _mock_client(
            {"candidates": [{"subscription_id": "does-not-exist", "insurer": "X"}]}
        )

        with patch("backend.services.ai_extract.AsyncOpenAI", return_value=mock_instance):
            resp = await client.post(f"/api/buckets/{bid}/insurances/detect-candidates")

        assert resp.status_code == 200
        assert resp.json()["candidates"] == []

    async def test_malformed_json_returns_empty_list(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client)
        await _create_sub(client, bid)
        await _configure_ai(client)

        mock_instance = MagicMock()
        mock_instance.chat.completions.create = AsyncMock(
            return_value=_MockResponse("not valid json{{{")
        )

        with patch("backend.services.ai_extract.AsyncOpenAI", return_value=mock_instance):
            resp = await client.post(f"/api/buckets/{bid}/insurances/detect-candidates")

        assert resp.status_code == 200
        assert resp.json()["candidates"] == []


# ---------------------------------------------------------------------------
# migrate-to-insurance
# ---------------------------------------------------------------------------


class TestMigrateToInsurance:
    async def test_creates_insurance_and_deletes_subscription(
        self, client: AsyncClient
    ) -> None:
        bid = await _create_bucket(client)
        sub = await _create_sub(
            client, bid, name="ARAG Rechtsschutz", provider="ARAG",
            interval="yearly", recurring_date="2024-03-01", amount=65.0,
        )

        resp = await client.post(
            f"/api/buckets/{bid}/subscriptions/{sub['id']}/migrate-to-insurance",
            json={"insurer": "ARAG", "policy_number": "POL-999"},
        )
        assert resp.status_code == 201, resp.text
        insurance = resp.json()
        assert insurance["name"] == "ARAG Rechtsschutz"
        assert insurance["insurer"] == "ARAG"
        assert insurance["policy_number"] == "POL-999"
        assert insurance["amount"] == pytest.approx(65.0)
        assert insurance["recurring_interval"] == "yearly"
        assert insurance["recurring_date"] == "2024-03-01"

        # Original subscription is gone
        resp = await client.get(f"/api/buckets/{bid}/subscriptions/{sub['id']}")
        assert resp.status_code == 404

        # And the insurance is listed
        resp = await client.get(f"/api/buckets/{bid}/insurances")
        names = [i["name"] for i in resp.json()]
        assert "ARAG Rechtsschutz" in names

    async def test_missing_subscription_returns_404(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client)
        resp = await client.post(
            f"/api/buckets/{bid}/subscriptions/does-not-exist/migrate-to-insurance",
            json={"insurer": "X"},
        )
        assert resp.status_code == 404

    async def test_empty_insurer_rejected(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client)
        sub = await _create_sub(client, bid)
        resp = await client.post(
            f"/api/buckets/{bid}/subscriptions/{sub['id']}/migrate-to-insurance",
            json={"insurer": "   "},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# ai-import/extract
# ---------------------------------------------------------------------------


class TestExtractFromDocument:
    async def test_not_configured_returns_400(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client)
        async with _NoAiConfig(client):
            resp = await client.post(
                f"/api/buckets/{bid}/ai-import/extract",
                files={"file": ("doc.pdf", b"%PDF-1.4 fake", "application/pdf")},
            )
        assert resp.status_code == 400

    async def test_disallowed_file_type_returns_415(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client)
        await _configure_ai(client)
        resp = await client.post(
            f"/api/buckets/{bid}/ai-import/extract",
            files={"file": ("doc.docx", b"content", "application/msword")},
        )
        assert resp.status_code == 415

    async def test_oversized_file_returns_413(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client)
        await _configure_ai(client)
        too_big = b"0" * (20 * 1024 * 1024 + 1)
        resp = await client.post(
            f"/api/buckets/{bid}/ai-import/extract",
            files={"file": ("big.pdf", too_big, "application/pdf")},
        )
        assert resp.status_code == 413

    async def test_genuinely_unreadable_pdf_returns_422(
        self, client: AsyncClient
    ) -> None:
        """No text layer AND the bytes aren't a real PDF pypdfium2 can render either."""
        bid = await _create_bucket(client)
        await _configure_ai(client)
        with patch("backend.services.document_content._extract_pdf_text", return_value=""):
            resp = await client.post(
                f"/api/buckets/{bid}/ai-import/extract",
                files={"file": ("scan.pdf", b"%PDF-1.4 not actually a pdf", "application/pdf")},
            )
        assert resp.status_code == 422

    async def test_pdf_with_no_text_falls_back_to_rendered_images(
        self, client: AsyncClient
    ) -> None:
        """A scanned/image-only PDF (no text layer) is rendered to page images
        and sent through the vision path instead of being rejected."""
        bid = await _create_bucket(client)
        await _configure_ai(client)

        mock_instance = _mock_client(
            {
                "records": [
                    {
                        "type": "insurance",
                        "confidence": "medium",
                        "fields": {
                            "name": "Household contents",
                            "insurer": "Allianz",
                            "recurring_interval": "yearly",
                            "amount": 210.0,
                            "currency": "EUR",
                        },
                    }
                ]
            }
        )

        with (
            patch("backend.services.document_content._extract_pdf_text", return_value=""),
            patch(
                "backend.services.document_content._render_pdf_pages_as_images",
                return_value=["data:image/png;base64,ZmFrZQ=="],
            ),
            patch("backend.services.ai_extract.AsyncOpenAI", return_value=mock_instance),
        ):
            resp = await client.post(
                f"/api/buckets/{bid}/ai-import/extract",
                files={"file": ("scanned_letter.pdf", b"%PDF-1.4 fake", "application/pdf")},
            )

        assert resp.status_code == 200, resp.text
        records = resp.json()["records"]
        assert len(records) == 1
        assert records[0]["fields"]["insurer"] == "Allianz"

        # Confirm it went through the vision path (image content, not plain text)
        call_kwargs = mock_instance.chat.completions.create.call_args.kwargs
        user_msg = call_kwargs["messages"][-1]
        assert isinstance(user_msg["content"], list)
        assert user_msg["content"][1]["type"] == "image_url"

    async def test_multi_page_pdf_sends_all_rendered_pages(
        self, client: AsyncClient
    ) -> None:
        bid = await _create_bucket(client)
        await _configure_ai(client)

        mock_instance = _mock_client({"records": []})

        with (
            patch("backend.services.document_content._extract_pdf_text", return_value=""),
            patch(
                "backend.services.document_content._render_pdf_pages_as_images",
                return_value=[
                    "data:image/png;base64,cGFnZTE=",
                    "data:image/png;base64,cGFnZTI=",
                ],
            ),
            patch("backend.services.ai_extract.AsyncOpenAI", return_value=mock_instance),
        ):
            resp = await client.post(
                f"/api/buckets/{bid}/ai-import/extract",
                files={"file": ("multipage.pdf", b"%PDF-1.4 fake", "application/pdf")},
            )

        assert resp.status_code == 200, resp.text
        call_kwargs = mock_instance.chat.completions.create.call_args.kwargs
        user_msg = call_kwargs["messages"][-1]
        image_parts = [p for p in user_msg["content"] if p["type"] == "image_url"]
        assert len(image_parts) == 2

    async def test_pdf_text_extracted_and_sent_to_ai(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client)
        await _configure_ai(client)

        mock_instance = _mock_client(
            {
                "records": [
                    {
                        "type": "insurance",
                        "confidence": "high",
                        "fields": {
                            "name": "Household contents",
                            "insurer": "Allianz",
                            "recurring_interval": "yearly",
                            "amount": 120.0,
                            "currency": "EUR",
                        },
                    }
                ]
            }
        )

        with (
            patch(
                "backend.services.document_content._extract_pdf_text",
                return_value="Versicherungsschein Allianz Hausrat 120 EUR jährlich " * 3,
            ),
            patch("backend.services.ai_extract.AsyncOpenAI", return_value=mock_instance),
        ):
            resp = await client.post(
                f"/api/buckets/{bid}/ai-import/extract",
                files={"file": ("policy.pdf", b"%PDF-1.4 fake", "application/pdf")},
            )

        assert resp.status_code == 200, resp.text
        records = resp.json()["records"]
        assert len(records) == 1
        assert records[0]["type"] == "insurance"
        assert records[0]["fields"]["insurer"] == "Allianz"

    async def test_image_sent_as_vision_content(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client)
        await _configure_ai(client)

        mock_instance = _mock_client(
            {
                "records": [
                    {
                        "type": "subscription",
                        "confidence": "medium",
                        "fields": {
                            "name": "Netflix",
                            "provider_name": "Netflix",
                            "recurring_interval": "monthly",
                            "amount": 9.99,
                            "currency": "EUR",
                        },
                    }
                ]
            }
        )

        with patch("backend.services.ai_extract.AsyncOpenAI", return_value=mock_instance):
            resp = await client.post(
                f"/api/buckets/{bid}/ai-import/extract",
                files={"file": ("receipt.png", b"\x89PNG fake bytes", "image/png")},
            )

        assert resp.status_code == 200, resp.text
        records = resp.json()["records"]
        assert records[0]["type"] == "subscription"

        # Confirm the image was sent as a vision content part, not plain text
        call_kwargs = mock_instance.chat.completions.create.call_args.kwargs
        user_msg = call_kwargs["messages"][-1]
        assert isinstance(user_msg["content"], list)
        assert user_msg["content"][1]["type"] == "image_url"
        assert user_msg["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")

    async def test_records_missing_required_fields_are_dropped(
        self, client: AsyncClient
    ) -> None:
        bid = await _create_bucket(client)
        await _configure_ai(client)

        mock_instance = _mock_client(
            {"records": [{"type": "insurance", "confidence": "low", "fields": {"insurer": "X"}}]}
        )

        with (
            patch(
                "backend.services.document_content._extract_pdf_text",
                return_value="Some extracted text " * 10,
            ),
            patch("backend.services.ai_extract.AsyncOpenAI", return_value=mock_instance),
        ):
            resp = await client.post(
                f"/api/buckets/{bid}/ai-import/extract",
                files={"file": ("policy.pdf", b"%PDF-1.4 fake", "application/pdf")},
            )

        assert resp.status_code == 200
        assert resp.json()["records"] == []


# ---------------------------------------------------------------------------
# extract_field_updates — unit tests (direct function calls, no HTTP)
# ---------------------------------------------------------------------------


class TestExtractFieldUpdates:
    async def test_returns_only_differing_fields(self) -> None:
        from backend.services.ai_extract import AiConfig, extract_field_updates

        existing = {
            "name": "Netflix", "provider_name": "Netflix", "recurring_interval": "monthly",
            "recurring_date": "2024-01-01", "end_date": None, "amount": 9.99,
            "currency": "EUR", "category_name": "Entertainment",
        }
        mock_instance = _mock_client(
            {"updates": {"amount": 12.99, "name": "Netflix"}}  # name matches -> dropped
        )
        config = AiConfig(api_url="http://x", api_key="k", model="m")

        with patch("backend.services.ai_extract.AsyncOpenAI", return_value=mock_instance):
            result = await extract_field_updates(
                existing, "subscription", {"kind": "text", "text": "doc"}, config
            )

        assert result == {"amount": 12.99}

    async def test_drops_unknown_field_names(self) -> None:
        from backend.services.ai_extract import AiConfig, extract_field_updates

        existing = {"name": "X", "insurer": "Y", "amount": 10.0}
        mock_instance = _mock_client(
            {"updates": {"amount": 20.0, "totally_made_up_field": "hallucinated"}}
        )
        config = AiConfig(api_url="http://x", api_key="k", model="m")

        with patch("backend.services.ai_extract.AsyncOpenAI", return_value=mock_instance):
            result = await extract_field_updates(
                existing, "insurance", {"kind": "text", "text": "doc"}, config
            )

        assert result == {"amount": 20.0}
        assert "totally_made_up_field" not in result

    async def test_drops_values_matching_existing_even_if_model_includes_them(self) -> None:
        """Defensive filter: even if the model ignores the 'omit unchanged'
        instruction, unchanged values are dropped server-side."""
        from backend.services.ai_extract import AiConfig, extract_field_updates

        existing = {"name": "Netflix", "amount": 9.99, "currency": "EUR"}
        mock_instance = _mock_client(
            {"updates": {"name": "Netflix", "amount": 9.99, "currency": "USD"}}
        )
        config = AiConfig(api_url="http://x", api_key="k", model="m")

        with patch("backend.services.ai_extract.AsyncOpenAI", return_value=mock_instance):
            result = await extract_field_updates(
                existing, "subscription", {"kind": "text", "text": "doc"}, config
            )

        assert result == {"currency": "USD"}

    async def test_invalid_recurring_interval_is_dropped(self) -> None:
        from backend.services.ai_extract import AiConfig, extract_field_updates

        existing = {"name": "X", "recurring_interval": "monthly"}
        mock_instance = _mock_client({"updates": {"recurring_interval": "fortnightly"}})
        config = AiConfig(api_url="http://x", api_key="k", model="m")

        with patch("backend.services.ai_extract.AsyncOpenAI", return_value=mock_instance):
            result = await extract_field_updates(
                existing, "subscription", {"kind": "text", "text": "doc"}, config
            )

        assert result == {}

    async def test_empty_updates_when_nothing_changed(self) -> None:
        from backend.services.ai_extract import AiConfig, extract_field_updates

        existing = {"name": "X", "amount": 5.0}
        mock_instance = _mock_client({"updates": {}})
        config = AiConfig(api_url="http://x", api_key="k", model="m")

        with patch("backend.services.ai_extract.AsyncOpenAI", return_value=mock_instance):
            result = await extract_field_updates(
                existing, "subscription", {"kind": "text", "text": "doc"}, config
            )

        assert result == {}

    async def test_malformed_json_returns_empty_dict(self) -> None:
        from backend.services.ai_extract import AiConfig, extract_field_updates

        mock_instance = MagicMock()
        mock_instance.chat.completions.create = AsyncMock(
            return_value=_MockResponse("not json{{{")
        )
        config = AiConfig(api_url="http://x", api_key="k", model="m")

        with patch("backend.services.ai_extract.AsyncOpenAI", return_value=mock_instance):
            result = await extract_field_updates(
                {"name": "X"}, "subscription", {"kind": "text", "text": "doc"}, config
            )

        assert result == {}


# ---------------------------------------------------------------------------
# Attachment-upload analysis integration — subscriptions and insurances
# ---------------------------------------------------------------------------


class TestAttachmentUploadAnalysis:
    async def test_subscription_upload_returns_suggested_updates(
        self, client: AsyncClient
    ) -> None:
        bid = await _create_bucket(client)
        sub = await _create_sub(client, bid, name="Netflix", amount=9.99)
        await _configure_ai(client)

        mock_instance = _mock_client({"updates": {"amount": 14.99}})

        with (
            patch(
                "backend.services.document_content._extract_pdf_text",
                return_value="Netflix renewal notice, new price 14.99 EUR/month " * 3,
            ),
            patch("backend.services.ai_extract.AsyncOpenAI", return_value=mock_instance),
        ):
            resp = await client.post(
                f"/api/buckets/{bid}/subscriptions/{sub['id']}/attachments",
                files={"file": ("renewal.pdf", b"%PDF-1.4 fake", "application/pdf")},
            )

        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["suggested_updates"] == {"amount": 14.99}
        assert body["attachment"]["filename"] == "renewal.pdf"

    async def test_insurance_upload_returns_suggested_updates(
        self, client: AsyncClient
    ) -> None:
        bid = await _create_bucket(client)
        ins = await _create_insurance_for_attachment_test(client, bid)
        await _configure_ai(client)

        mock_instance = _mock_client({"updates": {"amount": 99.0, "policy_number": "POL-NEW"}})

        with (
            patch(
                "backend.services.document_content._extract_pdf_text",
                return_value="Policy renewal, new premium 99.00 EUR, policy POL-NEW " * 3,
            ),
            patch("backend.services.ai_extract.AsyncOpenAI", return_value=mock_instance),
        ):
            resp = await client.post(
                f"/api/buckets/{bid}/insurances/{ins['id']}/attachments",
                files={"file": ("renewal.pdf", b"%PDF-1.4 fake", "application/pdf")},
            )

        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["suggested_updates"] == {"amount": 99.0, "policy_number": "POL-NEW"}

    async def test_analysis_failure_never_blocks_upload(self, client: AsyncClient) -> None:
        """AI call raising an exception must still let the attachment save successfully."""
        bid = await _create_bucket(client)
        sub = await _create_sub(client, bid)
        await _configure_ai(client)

        mock_instance = MagicMock()
        mock_instance.chat.completions.create = AsyncMock(side_effect=RuntimeError("boom"))

        with patch("backend.services.ai_extract.AsyncOpenAI", return_value=mock_instance):
            resp = await client.post(
                f"/api/buckets/{bid}/subscriptions/{sub['id']}/attachments",
                files={"file": ("invoice.png", b"\x89PNG fake bytes", "image/png")},
            )

        assert resp.status_code == 201, resp.text
        assert resp.json()["suggested_updates"] == {}

    async def test_docx_attachment_skips_analysis_but_still_uploads(
        self, client: AsyncClient
    ) -> None:
        bid = await _create_bucket(client)
        sub = await _create_sub(client, bid)
        await _configure_ai(client)

        resp = await client.post(
            f"/api/buckets/{bid}/subscriptions/{sub['id']}/attachments",
            files={
                "file": (
                    "invoice.docx", b"fake docx content",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )

        assert resp.status_code == 201, resp.text
        assert resp.json()["suggested_updates"] == {}

    async def test_not_configured_uploads_without_analysis(
        self, client: AsyncClient
    ) -> None:
        bid = await _create_bucket(client)
        sub = await _create_sub(client, bid)
        async with _NoAiConfig(client):
            resp = await client.post(
                f"/api/buckets/{bid}/subscriptions/{sub['id']}/attachments",
                files={"file": ("invoice.pdf", b"%PDF-1.4 fake", "application/pdf")},
            )
        assert resp.status_code == 201, resp.text
        assert resp.json()["suggested_updates"] == {}


async def _create_insurance_for_attachment_test(client: AsyncClient, bucket_id: str) -> dict:
    resp = await client.post(
        f"/api/buckets/{bucket_id}/insurances",
        json={
            "name": "Household contents", "insurer": "Allianz",
            "recurring_interval": "yearly", "recurring_date": "2024-01-01",
            "amount": 78.5,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()
