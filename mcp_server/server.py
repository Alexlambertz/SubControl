"""
SubControl MCP Server — stdio transport.

Run with:
    python -m mcp_server.server

Or after installing the package:
    subcontrol-mcp

Claude Desktop integration (claude_desktop_config.json):
    {
      "mcpServers": {
        "subcontrol": {
          "command": "python",
          "args": ["-m", "mcp_server.server"],
          "cwd": "/path/to/SubControl",
          "env": {
            "SUBCONTROL_API_URL": "http://localhost:8000",
            "SUBCONTROL_API_KEY": ""
          }
        }
      }
    }
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

from mcp_server import tools as t

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------------
# MCP server definition
# ---------------------------------------------------------------------------

server = Server("subcontrol")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """Declare all available tools to the MCP client."""
    return [
        types.Tool(
            name="list_subscriptions",
            description="List subscriptions. Optionally filter by bucket_id.",
            inputSchema={
                "type": "object",
                "properties": {
                    "bucket_id": {"type": "string", "description": "Filter by bucket UUID"},
                    "category_id": {"type": "integer", "description": "Filter by category ID"},
                },
            },
        ),
        types.Tool(
            name="get_subscription",
            description="Get a single subscription by ID.",
            inputSchema={
                "type": "object",
                "required": ["subscription_id", "bucket_id"],
                "properties": {
                    "subscription_id": {"type": "string"},
                    "bucket_id": {"type": "string"},
                },
            },
        ),
        types.Tool(
            name="create_subscription",
            description="Create a new subscription in a bucket.",
            inputSchema={
                "type": "object",
                "required": [
                    "bucket_id", "name", "provider_name",
                    "recurring_interval", "recurring_date", "amount",
                ],
                "properties": {
                    "bucket_id": {"type": "string"},
                    "name": {"type": "string"},
                    "provider_name": {"type": "string"},
                    "recurring_interval": {
                        "type": "string",
                        "enum": ["daily", "weekly", "monthly", "quarterly", "half-year", "yearly"],
                    },
                    "recurring_date": {
                        "type": "string",
                        "description": "Last payment date in YYYY-MM-DD format",
                    },
                    "amount": {"type": "number"},
                    "currency": {"type": "string", "default": "EUR"},
                    "category_name": {"type": "string"},
                },
            },
        ),
        types.Tool(
            name="update_subscription",
            description="Update one or more fields of an existing subscription.",
            inputSchema={
                "type": "object",
                "required": ["subscription_id", "bucket_id"],
                "properties": {
                    "subscription_id": {"type": "string"},
                    "bucket_id": {"type": "string"},
                    "name": {"type": "string"},
                    "provider_name": {"type": "string"},
                    "recurring_interval": {
                        "type": "string",
                        "enum": ["daily", "weekly", "monthly", "quarterly", "half-year", "yearly"],
                    },
                    "recurring_date": {"type": "string"},
                    "amount": {"type": "number"},
                    "currency": {"type": "string"},
                    "category_name": {"type": "string"},
                },
            },
        ),
        types.Tool(
            name="delete_subscription",
            description="Delete a subscription permanently.",
            inputSchema={
                "type": "object",
                "required": ["subscription_id", "bucket_id"],
                "properties": {
                    "subscription_id": {"type": "string"},
                    "bucket_id": {"type": "string"},
                },
            },
        ),
        types.Tool(
            name="list_buckets",
            description="List all available buckets.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="get_dashboard_summary",
            description=(
                "Get the spending dashboard summary. "
                "Use mode='average' for projected monthly costs or "
                "mode='real' with a month='YYYY-MM' for actual payments due."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["average", "real"],
                        "default": "average",
                    },
                    "month": {
                        "type": "string",
                        "description": "Required when mode=real. Format: YYYY-MM",
                    },
                    "bucket_id": {"type": "string"},
                },
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Dispatch a tool call to the appropriate handler."""
    try:
        result: Any
        if name == "list_subscriptions":
            result = await t.list_subscriptions(**arguments)
        elif name == "get_subscription":
            result = await t.get_subscription(**arguments)
        elif name == "create_subscription":
            result = await t.create_subscription(**arguments)
        elif name == "update_subscription":
            result = await t.update_subscription(**arguments)
        elif name == "delete_subscription":
            result = await t.delete_subscription(**arguments)
        elif name == "list_buckets":
            result = await t.list_buckets()
        elif name == "get_dashboard_summary":
            result = await t.get_dashboard_summary(**arguments)
        else:
            raise ValueError(f"Unknown tool: {name!r}")

        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as exc:
        logger.error("Tool %r failed: %s", name, exc)
        return [
            types.TextContent(
                type="text",
                text=json.dumps({"error": str(exc)}),
            )
        ]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    asyncio.run(stdio_server(server))


if __name__ == "__main__":
    main()
