# -*- coding: utf-8 -*-
"""MCP 桥 — 把 MCP 工具动态注册进 TOOLS（对编排层透明）

命名：mcp_<server>_<tool>，防止与本地工具冲突。risk 默认 exec（需 confirm）。
"""
from typing import Any, Callable

from core.logger import logger
from core.mcp.client import McpConnection
from core.tools.base import TOOLS


def _to_schema(name: str, mcp_tool) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": mcp_tool.description or name,
            "parameters": mcp_tool.input_schema or {"type": "object", "properties": {}},
        },
    }


def _make_mcp_func(conn: McpConnection, tool_name: str) -> Callable:
    async def call(**kwargs: Any) -> str:
        return await conn.call_tool(tool_name, kwargs)
    call.__name__ = tool_name
    return call


async def register_mcp_tools(conn: McpConnection) -> None:
    """把 conn 的全部工具注册进 TOOLS。"""
    tools = await conn.list_tools()
    for t in tools:
        name = f"mcp_{conn.cfg.name}_{t.name}"
        TOOLS.register(name, _make_mcp_func(conn, t.name), _to_schema(name, t), risk="exec")
    logger.info("MCP 注册 {} 个工具（server={}）", len(tools), conn.cfg.name)


async def unregister_mcp_tools(server_name: str) -> None:
    TOOLS.unregister_prefix(f"mcp_{server_name}_")
