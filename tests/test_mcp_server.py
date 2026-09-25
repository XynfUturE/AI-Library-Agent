"""The optional MCP server must expose exactly the agent's tools."""

import asyncio

import pytest

pytest.importorskip(
    "mcp.server.mcpserver",
    reason="optional dependency: pip install -r requirements-mcp.txt",
)

from agent.auth import login_demo_user
from agent.core import TOOL_DEFINITIONS

from scripts.mcp_server import build_server


def test_mcp_server_exposes_the_agent_tools(app_database):

    demo = login_demo_user()

    assert demo["success"] is True, demo

    server = build_server(
        demo["user"]["id"]
    )

    tools = asyncio.run(
        server.list_tools()
    )

    assert {
        tool.name
        for tool in tools
    } == {
        definition["function"]["name"]
        for definition in TOOL_DEFINITIONS
    }


def test_mcp_server_rejects_an_unknown_user(app_database):

    with pytest.raises(SystemExit):

        build_server(999999)
