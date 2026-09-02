# -*- coding: utf-8 -*-
"""测试用 MCP 回显服务器 — 供 MCP 客户端测试/冒烟（mcp 2.0 lowlevel API，stdio）

Test MCP echo server — for MCP client testing / smoke tests (mcp 2.0 low-level API, stdio)."""
import asyncio

from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
)

_TOOLS = [
    Tool(name="echo", description="原样返回输入",
         input_schema={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}),
    Tool(name="add", description="两数相加",
         input_schema={"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}}, "required": ["a", "b"]}),
]


async def handle_list_tools(ctx: ServerRequestContext, params: PaginatedRequestParams | None) -> ListToolsResult:
    """返回工具列表（echo / add）。

    Return the tool list (echo / add).
    """
    return ListToolsResult(tools=_TOOLS)


async def handle_call_tool(ctx: ServerRequestContext, params: CallToolRequestParams) -> CallToolResult:
    """处理工具调用：echo 原样返回输入，add 求和，未知工具返回错误。

    Handle tool calls: echo returns the input as-is, add sums two integers, and unknown tools return an error.
    """
    args = params.arguments or {}
    if params.name == "echo":
        return CallToolResult(content=[TextContent(type="text", text=f"echo:{args.get('text', '')}")])
    if params.name == "add":
        return CallToolResult(content=[TextContent(type="text", text=str(int(args.get("a", 0)) + int(args.get("b", 0))))])
    return CallToolResult(content=[TextContent(type="text", text="unknown tool")], is_error=True)


server = Server("echo", on_list_tools=handle_list_tools, on_call_tool=handle_call_tool)


async def main() -> None:
    """通过 stdio 启动并运行 MCP 服务器。

    Start and run the MCP server over stdio.
    """
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
