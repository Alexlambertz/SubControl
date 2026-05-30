# MCP Server

SubControl ships a standalone MCP (Model Context Protocol) server that exposes subscription management as tools to any MCP-compatible AI agent (Claude Desktop, etc.).

## Running

```bash
cd mcp_server
pip install -e .
python server.py
```

Or as an MCP tool entry point (stdio transport):

```json
{
  "mcpServers": {
    "subcontrol": {
      "command": "python",
      "args": ["/path/to/SubControl/mcp_server/server.py"],
      "env": {
        "SUBCONTROL_API_URL": "http://localhost:8000",
        "SUBCONTROL_API_KEY": "your-api-key"
      }
    }
  }
}
```

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SUBCONTROL_API_URL` | `http://localhost:8000` | SubControl backend URL |
| `SUBCONTROL_API_KEY` | (empty) | Bearer token for auth |

## Tools

### `list_subscriptions`
List subscriptions, optionally filtered.

| Arg | Required | Description |
|-----|----------|-------------|
| `bucket_id` | No | Filter to a specific bucket (if omitted, all buckets) |
| `category_id` | No | Filter by category |
| `provider_id` | No | Filter by provider |

### `get_subscription`
Get a single subscription by ID.

| Arg | Required |
|-----|----------|
| `subscription_id` | Yes |
| `bucket_id` | Yes |

### `create_subscription`
Create a new subscription.

| Arg | Required |
|-----|----------|
| `bucket_id` | Yes |
| `name` | Yes |
| `recurring_interval` | Yes |
| `amount` | Yes |
| `provider_name` | No |
| `recurring_date` | No |
| `currency` | No (default EUR) |
| `category_name` | No |

### `update_subscription`
Update an existing subscription (all fields except IDs are optional).

### `delete_subscription`
Delete a subscription. Returns `{"deleted": true}`.

### `list_buckets`
List all buckets.

### `get_dashboard_summary`
Get the spending summary.

| Arg | Required | Description |
|-----|----------|-------------|
| `mode` | No | `average` (default) or `real` |
| `month` | No | `YYYY-MM` (for real mode) |
| `bucket_id` | No | Filter to a bucket |
