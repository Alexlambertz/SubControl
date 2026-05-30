# AI Chat

**Endpoint:** `POST /api/chat/message`

Streams an LLM response using Server-Sent Events (SSE).

## Request

```json
{
  "message": "How much am I spending on streaming?",
  "bucket_id": "optional-bucket-id"
}
```

## Response (SSE stream)

```
data: {"content": "You are spending "}
data: {"content": "€25.98 per month on streaming."}
data: [DONE]
```

Each `data:` line contains either a JSON object with a `content` key, or the terminal `[DONE]` sentinel.

## System prompt

The AI is given context about the user's current subscriptions at the start of every conversation:

```
You are SubControl, an AI assistant for managing subscriptions...

The user has the following subscriptions:
- Netflix (Netflix): 15.99 EUR/monthly [Streaming]
- Spotify (Spotify): 9.99 EUR/monthly [Music]
```

## Tool calls

The model can call two server-side tools:

### `create_subscription`
Creates a new subscription in the specified bucket. Required args: `bucket_id`, `name`, `recurring_interval`, `amount`.

### `update_subscription`
Updates fields on an existing subscription. Required args: `subscription_id`, `bucket_id`.

Tool calls are executed server-side before the final streaming response is sent.

## Configuration

AI settings are stored in the `app_settings` table and configurable via `PUT /api/settings/{key}` (admin only):

| Key | Description | Default |
|-----|-------------|---------|
| `ai_api_url` | OpenAI-compatible base URL | `` (empty — AI disabled) |
| `ai_api_key` | API key | `` |
| `ai_model` | Model name | `gpt-4o-mini` |

Point `ai_api_url` at any OpenAI-compatible endpoint (OpenAI, Ollama, LM Studio, etc.).

Environment variables override settings: `AI_API_URL`, `AI_API_KEY`, `AI_MODEL`.

## Error states

- `ai_api_url` is empty → streams "AI is not configured" message
- `openai` package not installed → streams installation notice
- API error → streams the error message
