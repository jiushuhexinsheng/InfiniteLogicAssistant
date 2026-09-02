# -*- coding: utf-8 -*-
"""MCP 客户端 — 连接外部 MCP server（stdio transport），枚举/调用其工具。

MCP client — connects to an external MCP server (stdio transport) to list and call its tools.
"""
from dataclasses import dataclass
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@dataclass
class McpServerCfg:
    """MCP server 连接配置。

    Connection configuration for an MCP server.

    Attributes:
        name: server 名称（唯一标识）。 / The server name (unique identifier).
        command: 启动 server 的可执行命令。 / The executable command that starts the server.
        args: 传给命令的参数列表。 / The argument list passed to the command.
    """

    name: str
    command: str
    args: list[str]


@dataclass
class McpTool:
    """MCP 工具元信息。

    Metadata of an MCP tool.

    Attributes:
        name: 工具名称。 / The tool name.
        description: 工具描述。 / The tool description.
        input_schema: 工具入参 JSON Schema。 / The tool's input JSON Schema.
    """

    name: str
    description: str
    input_schema: dict


class McpConnection:
    """管理单个 MCP server 的连接生命周期（stdio）。

    Manages the connection lifecycle of a single MCP server (stdio).
    """

    def __init__(self, cfg: McpServerCfg):
        """保存 server 配置并初始化连接状态。

        Store the server configuration and initialize the connection state.

        Args:
            cfg: MCP server 连接配置。 / The MCP server connection configuration.
        """
        self.cfg = cfg
        self._stdio_ctx: Any = None
        self._session_ctx: Any = None
        self._session: ClientSession | None = None

    async def connect(self) -> None:
        """建立 stdio 连接并初始化 MCP 会话。

        Establish the stdio connection and initialize the MCP session.
        """
        params = StdioServerParameters(command=self.cfg.command, args=self.cfg.args)
        self._stdio_ctx = stdio_client(params)
        read, write = await self._stdio_ctx.__aenter__()
        self._session_ctx = ClientSession(read, write)
        self._session = await self._session_ctx.__aenter__()
        await self._session.initialize()

    async def list_tools(self) -> list[McpTool]:
        """枚举 server 暴露的全部工具。

        List all tools exposed by the server.

        Returns:
            工具元信息列表。 / A list of tool metadata.
        """
        assert self._session is not None
        res = await self._session.list_tools()
        return [McpTool(t.name, t.description or "", dict(t.input_schema or {})) for t in res.tools]

    async def call_tool(self, name: str, args: dict) -> str:
        """调用指定工具并把结果内容拼接为文本。

        Call the named tool and join the result content into text.

        Args:
            name: 工具名称。 / The tool name.
            args: 工具入参。 / The tool arguments.

        Returns:
            拼接后的结果文本。 / The joined result text.
        """
        assert self._session is not None
        result = await self._session.call_tool(name, args)
        parts = []
        for block in result.content or []:
            parts.append(getattr(block, "text", str(block)))
        return "\n".join(parts)

    async def close(self) -> None:
        """关闭 MCP 会话与 stdio 连接，并清空状态。

        Close the MCP session and stdio connection, and reset the state.
        """
        if self._session_ctx is not None:
            await self._session_ctx.__aexit__(None, None, None)
            self._session_ctx = None
        if self._stdio_ctx is not None:
            await self._stdio_ctx.__aexit__(None, None, None)
            self._stdio_ctx = None
        self._session = None
