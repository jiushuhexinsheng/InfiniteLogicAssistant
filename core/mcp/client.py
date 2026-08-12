# -*- coding: utf-8 -*-
"""MCP 客户端 — 连接外部 MCP server（stdio transport），枚举/调用其工具"""
from dataclasses import dataclass
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@dataclass
class McpServerCfg:
    name: str
    command: str
    args: list[str]


@dataclass
class McpTool:
    name: str
    description: str
    input_schema: dict


class McpConnection:
    def __init__(self, cfg: McpServerCfg):
        self.cfg = cfg
        self._stdio_ctx = None
        self._session_ctx = None
        self._session: ClientSession | None = None

    async def connect(self) -> None:
        params = StdioServerParameters(command=self.cfg.command, args=self.cfg.args)
        self._stdio_ctx = stdio_client(params)
        read, write = await self._stdio_ctx.__aenter__()
        self._session_ctx = ClientSession(read, write)
        self._session = await self._session_ctx.__aenter__()
        await self._session.initialize()

    async def list_tools(self) -> list[McpTool]:
        assert self._session is not None
        res = await self._session.list_tools()
        return [McpTool(t.name, t.description or "", dict(t.input_schema or {})) for t in res.tools]

    async def call_tool(self, name: str, args: dict) -> str:
        assert self._session is not None
        result = await self._session.call_tool(name, args)
        parts = []
        for block in result.content or []:
            parts.append(getattr(block, "text", str(block)))
        return "\n".join(parts)

    async def close(self) -> None:
        if self._session_ctx is not None:
            await self._session_ctx.__aexit__(None, None, None)
            self._session_ctx = None
        if self._stdio_ctx is not None:
            await self._stdio_ctx.__aexit__(None, None, None)
            self._stdio_ctx = None
        self._session = None
