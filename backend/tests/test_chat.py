"""
Tests for the AI chat endpoint.

We mock the openai.AsyncOpenAI client to avoid real network calls.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Streaming mock helpers
# ---------------------------------------------------------------------------

class _MockDelta:
    """Simulates a streaming delta object."""
    def __init__(self, content: str | None = None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _MockChoice:
    """Simulates a streaming choice with delta + finish_reason."""
    def __init__(self, content: str | None = None, tool_calls=None, finish_reason=None):
        self.delta = _MockDelta(content, tool_calls)
        self.finish_reason = finish_reason


class _MockChunk:
    """Simulates a streaming chunk with a single choice."""
    def __init__(self, content: str | None = None, finish_reason: str | None = None):
        self.choices = [_MockChoice(content=content, finish_reason=finish_reason)]


def _make_tool_call_delta(index: int, call_id: str, fn_name: str, fn_args: str):
    """Build a MagicMock tool-call delta as the OpenAI SDK would produce."""
    tc_delta = MagicMock()
    tc_delta.index = index
    tc_delta.id = call_id
    tc_delta.function = MagicMock()
    tc_delta.function.name = fn_name
    tc_delta.function.arguments = fn_args
    return tc_delta


class TestChatEndpoint:
    """Tests for POST /api/chat/message."""

    async def test_chat_no_ai_url_returns_config_message(self, client: AsyncClient):
        """When ai_api_url is empty, returns a configuration prompt."""
        # Ensure ai_api_url is blank (default from seeded settings)
        res = await client.post(
            "/api/chat/message",
            json={"message": "Hello"},
        )
        assert res.status_code == 200
        body = res.text
        assert "not configured" in body.lower() or "ai_api_url" in body.lower()

    async def test_chat_streams_response(self, client: AsyncClient):
        """With a mocked OpenAI client, SSE chunks are streamed."""
        await client.put(
            "/api/settings/ai_api_url",
            json={"value": "https://api.openai.com/v1"},
        )
        await client.put(
            "/api/settings/ai_api_key",
            json={"value": "test-key"},
        )
        await client.put(
            "/api/settings/ai_model",
            json={"value": "gpt-4o-mini"},
        )

        # Single streaming call — yields text chunks, no tool calls
        async def fake_create(**kwargs):
            async def _gen():
                yield _MockChunk("Hello")
                yield _MockChunk(" world")
                yield _MockChunk("!", finish_reason="stop")
            return _gen()

        mock_openai_instance = MagicMock()
        mock_openai_instance.chat.completions.create = AsyncMock(side_effect=fake_create)

        with patch("backend.services.ai_chat.AsyncOpenAI", return_value=mock_openai_instance):
            res = await client.post(
                "/api/chat/message",
                json={"message": "Say hello"},
            )

        assert res.status_code == 200
        assert "Hello" in res.text
        assert "[DONE]" in res.text

    async def test_chat_includes_subscription_context(self, client: AsyncClient):
        """The system prompt sent to the AI contains the user's subscriptions."""
        # Create a bucket + subscription first
        bucket_res = await client.post("/api/buckets", json={"name": "Personal"})
        bucket_id = bucket_res.json()["id"]
        await client.post(
            f"/api/buckets/{bucket_id}/subscriptions",
            json={
                "name": "Netflix",
                "provider_name": "Netflix",
                "recurring_interval": "monthly",
                "amount": 9.99,
                "currency": "EUR",
            },
        )

        await client.put(
            "/api/settings/ai_api_url",
            json={"value": "https://api.openai.com/v1"},
        )

        captured_messages: list = []

        async def capture_create(**kwargs):
            # Always streaming — capture messages from every call
            captured_messages.extend(kwargs.get("messages", []))
            async def _gen():
                yield _MockChunk("done", finish_reason="stop")
            return _gen()

        mock_instance = MagicMock()
        mock_instance.chat.completions.create = AsyncMock(side_effect=capture_create)

        with patch("backend.services.ai_chat.AsyncOpenAI", return_value=mock_instance):
            await client.post(
                "/api/chat/message",
                json={"message": "What subscriptions do I have?"},
            )

        assert captured_messages, "OpenAI client was not called"
        system_prompt = captured_messages[0]["content"]
        assert "Netflix" in system_prompt

    async def test_chat_tool_call_creates_subscription(self, client: AsyncClient):
        """A create_subscription tool call from the model is executed."""
        bucket_res = await client.post("/api/buckets", json={"name": "Work"})
        bucket_id = bucket_res.json()["id"]

        await client.put(
            "/api/settings/ai_api_url",
            json={"value": "https://api.openai.com/v1"},
        )

        tool_args = json.dumps({
            "bucket_id": bucket_id,
            "name": "Spotify",
            "provider_name": "Spotify",
            "recurring_interval": "monthly",
            "amount": 9.99,
            "currency": "EUR",
        })

        call_count = 0

        async def mock_create(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First streaming call: yield a tool-call delta, then finish_reason=tool_calls
                async def _first_stream():
                    # Chunk carrying the tool-call delta
                    tc_delta = _make_tool_call_delta(
                        index=0,
                        call_id="call_abc123",
                        fn_name="create_subscription",
                        fn_args=tool_args,
                    )
                    tc_choice = MagicMock()
                    tc_choice.delta = MagicMock()
                    tc_choice.delta.content = None
                    tc_choice.delta.tool_calls = [tc_delta]
                    tc_choice.finish_reason = None

                    tc_chunk = MagicMock()
                    tc_chunk.choices = [tc_choice]
                    yield tc_chunk

                    # Final chunk that signals tool_calls
                    final_choice = MagicMock()
                    final_choice.delta = MagicMock()
                    final_choice.delta.content = None
                    final_choice.delta.tool_calls = None
                    final_choice.finish_reason = "tool_calls"

                    final_chunk = MagicMock()
                    final_chunk.choices = [final_choice]
                    yield final_chunk

                return _first_stream()
            else:
                # Second streaming call (follow-up after tool execution)
                async def _second_stream():
                    yield _MockChunk("Spotify added!", finish_reason="stop")
                return _second_stream()

        mock_instance = MagicMock()
        mock_instance.chat.completions.create = AsyncMock(side_effect=mock_create)

        with patch("backend.services.ai_chat.AsyncOpenAI", return_value=mock_instance):
            res = await client.post(
                "/api/chat/message",
                json={"message": "Add Spotify for 9.99 per month"},
            )

        assert res.status_code == 200

        # Verify subscription was actually created in the DB
        subs_res = await client.get(f"/api/buckets/{bucket_id}/subscriptions")
        names = [s["name"] for s in subs_res.json()]
        assert "Spotify" in names
