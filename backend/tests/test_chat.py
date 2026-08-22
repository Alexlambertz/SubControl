"""
Tests for the AI chat endpoint.

We mock the openai.AsyncOpenAI client to avoid real network calls.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
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
        """When ai_api_url is empty in both DB and env, returns a config prompt."""
        import backend.config as cfg
        # Blank out both the DB value and the env-var fallback so neither
        # source provides a URL, which should trigger the "not configured" path.
        original_url = cfg.settings.ai_api_url
        cfg.settings.ai_api_url = ""
        try:
            # Ensure DB entry is also blank
            await client.put("/api/settings/ai_api_url", json={"value": ""})
            res = await client.post(
                "/api/chat/message",
                json={"message": "Hello"},
            )
            assert res.status_code == 200
            body = res.text
            assert "not configured" in body.lower() or "ai_api_url" in body.lower()
        finally:
            cfg.settings.ai_api_url = original_url

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

    async def test_chat_includes_insurance_context(self, client: AsyncClient):
        """The system prompt sent to the AI contains the user's insurance policies."""
        bucket_res = await client.post("/api/buckets", json={"name": "InsBucket"})
        bucket_id = bucket_res.json()["id"]
        await client.post(
            f"/api/buckets/{bucket_id}/insurances",
            json={
                "name": "Household contents",
                "insurer": "Allianz",
                "recurring_interval": "yearly",
                "amount": 120.0,
                "currency": "EUR",
            },
        )

        await client.put(
            "/api/settings/ai_api_url",
            json={"value": "https://api.openai.com/v1"},
        )

        captured_messages: list = []

        async def capture_create(**kwargs):
            captured_messages.extend(kwargs.get("messages", []))
            async def _gen():
                yield _MockChunk("done", finish_reason="stop")
            return _gen()

        mock_instance = MagicMock()
        mock_instance.chat.completions.create = AsyncMock(side_effect=capture_create)

        with patch("backend.services.ai_chat.AsyncOpenAI", return_value=mock_instance):
            await client.post(
                "/api/chat/message",
                json={"message": "What insurance policies do I have?"},
            )

        assert captured_messages, "OpenAI client was not called"
        system_prompt = captured_messages[0]["content"]
        assert "Household contents" in system_prompt
        assert "Allianz" in system_prompt

    async def test_chat_tool_call_creates_insurance(self, client: AsyncClient):
        """A create_insurance tool call from the model is executed."""
        bucket_res = await client.post("/api/buckets", json={"name": "InsWork"})
        bucket_id = bucket_res.json()["id"]

        await client.put(
            "/api/settings/ai_api_url",
            json={"value": "https://api.openai.com/v1"},
        )

        tool_args = json.dumps({
            "bucket_id": bucket_id,
            "name": "Liability insurance",
            "insurer": "HUK24",
            "recurring_interval": "yearly",
            "amount": 65.0,
            "currency": "EUR",
            "owner_name": "Alex",
        })

        call_count = 0

        async def mock_create(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                async def _first_stream():
                    tc_delta = _make_tool_call_delta(
                        index=0,
                        call_id="call_ins123",
                        fn_name="create_insurance",
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
                async def _second_stream():
                    yield _MockChunk("Liability insurance added!", finish_reason="stop")
                return _second_stream()

        mock_instance = MagicMock()
        mock_instance.chat.completions.create = AsyncMock(side_effect=mock_create)

        with patch("backend.services.ai_chat.AsyncOpenAI", return_value=mock_instance):
            res = await client.post(
                "/api/chat/message",
                json={"message": "Add liability insurance with HUK24 for 65 per year, owned by Alex"},
            )

        assert res.status_code == 200

        ins_res = await client.get(f"/api/buckets/{bucket_id}/insurances")
        insurances = ins_res.json()
        names = [i["name"] for i in insurances]
        assert "Liability insurance" in names
        created = next(i for i in insurances if i["name"] == "Liability insurance")
        assert created["insurer"] == "HUK24"
        assert created["owner_name"] == "Alex"


class TestChatConversations:
    """Tests for conversation persistence and the conversation CRUD endpoints."""

    async def _configure_ai(self, client: AsyncClient) -> None:
        await client.put(
            "/api/settings/ai_api_url",
            json={"value": "https://api.openai.com/v1"},
        )

    def _mock_instance(self, reply: str = "Hi there!"):
        async def fake_create(**kwargs):
            async def _gen():
                yield _MockChunk(reply, finish_reason="stop")
            return _gen()

        instance = MagicMock()
        instance.chat.completions.create = AsyncMock(side_effect=fake_create)
        return instance

    async def test_message_without_conversation_id_creates_one(
        self, client: AsyncClient
    ) -> None:
        await self._configure_ai(client)
        with patch(
            "backend.services.ai_chat.AsyncOpenAI",
            return_value=self._mock_instance(),
        ):
            res = await client.post(
                "/api/chat/message",
                json={"message": "How much do I spend per month?"},
            )
        assert res.status_code == 200
        conv_id = res.headers.get("x-conversation-id")
        assert conv_id

        list_res = await client.get("/api/chat/conversations")
        assert list_res.status_code == 200
        convs = list_res.json()
        assert any(c["id"] == conv_id for c in convs)
        found = next(c for c in convs if c["id"] == conv_id)
        assert found["title"] == "How much do I spend per month?"

    async def test_conversation_detail_includes_both_messages(
        self, client: AsyncClient
    ) -> None:
        await self._configure_ai(client)
        with patch(
            "backend.services.ai_chat.AsyncOpenAI",
            return_value=self._mock_instance("Hello!"),
        ):
            res = await client.post(
                "/api/chat/message",
                json={"message": "Hi"},
            )
        conv_id = res.headers["x-conversation-id"]

        detail_res = await client.get(f"/api/chat/conversations/{conv_id}")
        assert detail_res.status_code == 200
        body = detail_res.json()
        roles = [m["role"] for m in body["messages"]]
        contents = [m["content"] for m in body["messages"]]
        assert roles == ["user", "assistant"]
        assert contents == ["Hi", "Hello!"]

    async def test_second_message_reuses_conversation_id(
        self, client: AsyncClient
    ) -> None:
        await self._configure_ai(client)
        with patch(
            "backend.services.ai_chat.AsyncOpenAI",
            return_value=self._mock_instance("First reply"),
        ):
            res1 = await client.post(
                "/api/chat/message",
                json={"message": "First message"},
            )
        conv_id = res1.headers["x-conversation-id"]

        with patch(
            "backend.services.ai_chat.AsyncOpenAI",
            return_value=self._mock_instance("Second reply"),
        ):
            res2 = await client.post(
                "/api/chat/message",
                json={"message": "Second message", "conversation_id": conv_id},
            )
        assert res2.headers["x-conversation-id"] == conv_id

        detail_res = await client.get(f"/api/chat/conversations/{conv_id}")
        contents = [m["content"] for m in detail_res.json()["messages"]]
        assert contents == ["First message", "First reply", "Second message", "Second reply"]

        # Only one conversation was created, not two
        list_res = await client.get("/api/chat/conversations")
        matching = [c for c in list_res.json() if c["id"] == conv_id]
        assert len(matching) == 1

    async def test_delete_conversation_removes_it(self, client: AsyncClient) -> None:
        await self._configure_ai(client)
        with patch(
            "backend.services.ai_chat.AsyncOpenAI",
            return_value=self._mock_instance(),
        ):
            res = await client.post(
                "/api/chat/message",
                json={"message": "Delete me later"},
            )
        conv_id = res.headers["x-conversation-id"]

        del_res = await client.delete(f"/api/chat/conversations/{conv_id}")
        assert del_res.status_code == 204

        get_res = await client.get(f"/api/chat/conversations/{conv_id}")
        assert get_res.status_code == 404

    async def test_missing_conversation_returns_404(self, client: AsyncClient) -> None:
        res = await client.get("/api/chat/conversations/does-not-exist")
        assert res.status_code == 404

    async def test_conversation_scoped_to_owning_user(
        self, client: AsyncClient, db: aiosqlite.Connection
    ) -> None:
        """A conversation belonging to a different user is invisible to the dev user."""
        await db.execute(
            "INSERT INTO users (id, username) VALUES (?, ?)",
            ("some-other-user-id", "someone-else"),
        )
        await db.execute(
            "INSERT INTO chat_conversations (id, user_id, title) VALUES (?, ?, ?)",
            ("other-conv-id", "some-other-user-id", "Someone else's chat"),
        )
        await db.commit()

        list_res = await client.get("/api/chat/conversations")
        ids = [c["id"] for c in list_res.json()]
        assert "other-conv-id" not in ids

        get_res = await client.get("/api/chat/conversations/other-conv-id")
        assert get_res.status_code == 404

        del_res = await client.delete("/api/chat/conversations/other-conv-id")
        assert del_res.status_code == 404
