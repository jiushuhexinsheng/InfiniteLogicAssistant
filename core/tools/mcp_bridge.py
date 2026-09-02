# -*- coding: utf-8 -*-
"""MCP 桥 — 把 MCP 工具动态注册进 TOOLS（对编排层透明）

命名：mcp_<server>_<tool>，防止与本地工具冲突。risk 默认 exec（需 confirm）。

MCP bridge — dynamically registers MCP tools into TOOLS (transparent to the orchestration layer).
Naming: mcp_<server>_<tool> to avoid conflicts with local tools. risk defaults to exec (requires confirm).
"""
from typing import Any, Callable

from core.logger import logger
from core.mcp.client import McpConnection
from core.tools.base import TOOLS


def _to_schema(name: str, mcp_tool) -> dict:
    """把 MCP 工具转换为 OpenAI 函数 schema。Convert an MCP tool into an OpenAI function schema.

    Args:
        name: 注册名称。Registered name.
        mcp_tool: MCP 工具对象。MCP tool object.

    Returns:
        OpenAI 函数 schema。OpenAI function schema.
    """
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": mcp_tool.description or name,
            "parameters": mcp_tool.input_schema or {"type": "object", "properties": {}},
        },
    }


def _make_mcp_func(conn: McpConnection, tool_name: str) -> Callable:
    """为 MCP 工具生成异步调用函数。Create an async call function for an MCP tool.

    Args:
        conn: MCP 连接。MCP connection.
        tool_name: 工具名。Tool name.

    Returns:
        异步调用函数。Async call function.
    """
    async def call(**kwargs: Any) -> str:
        return await conn.call_tool(tool_name, kwargs)
    call.__name__ = tool_name
    return call


async def register_mcp_tools(conn: McpConnection) -> None:
    """把 conn 的全部工具注册进 TOOLS。Register all tools of conn into TOOLS.

    Args:
        conn: MCP 连接。MCP connection.
    """
    tools = await conn.list_tools()
    for t in tools:
        name = f"mcp_{conn.cfg.name}_{t.name}"
        TOOLS.register(name, _make_mcp_func(conn, t.name), _to_schema(name, t), risk="exec")
    logger.info("MCP 注册 {} 个工具（server={}）", len(tools), conn.cfg.name)


async def unregister_mcp_tools(server_name: str) -> None:
    """注销指定 MCP 服务器的全部工具。Unregister all tools of the given MCP server.

    Args:
        server_name: MCP 服务器名。MCP server name.
    """
    TOOLS.unregister_prefix(f"mcp_{server_name}_")
