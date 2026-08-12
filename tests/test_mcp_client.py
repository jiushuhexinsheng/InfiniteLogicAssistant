# -*- coding: utf-8 -*-
import sys
from pathlib import Path

import pytest

from core.mcp.client import McpConnection, McpServerCfg

ROOT = Path(__file__).resolve().parent.parent
ECHO_SERVER = str(ROOT / "scripts" / "mcp_echo_server.py")


@pytest.mark.asyncio
async def test_mcp_list_tools():
    c = McpConnection(McpServerCfg(name="echo", command=sys.executable, args=[ECHO_SERVER]))
    await c.connect()
    try:
        tools = await c.list_tools()
        names = {t.name for t in tools}
        assert {"echo", "add"} <= names
        echo_tool = next(t for t in tools if t.name == "echo")
        assert "text" in echo_tool.input_schema["properties"]
    finally:
        await c.close()


@pytest.mark.asyncio
async def test_mcp_call_tool():
    c = McpConnection(McpServerCfg(name="echo", command=sys.executable, args=[ECHO_SERVER]))
    await c.connect()
    try:
        r = await c.call_tool("echo", {"text": "hi"})
        assert "echo:hi" in r
        r2 = await c.call_tool("add", {"a": 1, "b": 2})
        assert "3" in r2
    finally:
        await c.close()
