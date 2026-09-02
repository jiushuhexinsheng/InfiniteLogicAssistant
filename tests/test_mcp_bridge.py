# -*- coding: utf-8 -*-
"""测试 MCP 工具桥接的注册、调用转发与注销功能。
Tests the MCP tool bridge: registration, call forwarding, and unregistration.
"""
import sys
from pathlib import Path

import pytest

from core.mcp.client import McpConnection, McpServerCfg
from core.tools import TOOLS
from core.tools.mcp_bridge import register_mcp_tools, unregister_mcp_tools

ROOT = Path(__file__).resolve().parent.parent
ECHO = str(ROOT / "scripts" / "mcp_echo_server.py")


@pytest.mark.asyncio
async def test_register_call_unregister():
    """测试注册 MCP 工具后可以调用并注销。Tests registering MCP tools, calling them, and unregistering them."""
    c = McpConnection(McpServerCfg("echo", sys.executable, [ECHO]))
    await c.connect()
    try:
        await register_mcp_tools(c)
        assert TOOLS.has("mcp_echo_echo")
        assert TOOLS.has("mcp_echo_add")
        # schema 带前缀名，发给 LLM
        names = {s["function"]["name"] for s in TOOLS.schemas()}
        assert "mcp_echo_add" in names
        # 调用转发
        out = await TOOLS.acall("mcp_echo_add", {"a": 3, "b": 4})
        assert out == "7"
    finally:
        await c.close()
        await unregister_mcp_tools("echo")
    assert not TOOLS.has("mcp_echo_echo")
    assert not TOOLS.has("mcp_echo_add")
