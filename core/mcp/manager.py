# -*- coding: utf-8 -*-
"""MCP 生命周期管理 — 启动/停止全部 MCP server，并把工具注册进 TOOLS。

MCP lifecycle management — starts/stops all MCP servers and registers their tools into TOOLS.
"""
from core import config
from core.logger import logger
from core.mcp.client import McpConnection, McpServerCfg
from core.tools.mcp_bridge import register_mcp_tools, unregister_mcp_tools


class McpManager:
    """管理全部 MCP server 连接的生命周期。

    Manages the lifecycle of all MCP server connections.
    """

    def __init__(self) -> None:
        """初始化连接列表为空。

        Initialize the connection list as empty.
        """
        self._conns: list[McpConnection] = []

    async def start_all(self) -> None:
        """启动配置中的全部 MCP server，并将可用工具注册进 TOOLS。

        Start all MCP servers from the configuration and register their available tools into TOOLS.
        """
        for s in config.settings.mcp.servers:
            c = McpConnection(McpServerCfg(s.name, s.command, s.args))
            try:
                await c.connect()
                await register_mcp_tools(c)
                self._conns.append(c)
            except Exception as e:
                logger.warning("MCP server '{}' 连接失败: {}", s.name, e)

    async def stop_all(self) -> None:
        """注销全部工具并关闭所有 MCP 连接。

        Unregister all tools and close every MCP connection.
        """
        for c in self._conns:
            try:
                await unregister_mcp_tools(c.cfg.name)
            except Exception:
                pass
            try:
                await c.close()
            except Exception:
                pass
        self._conns = []

    def list_connections(self) -> list[str]:
        """返回当前已连接 server 的名称列表。

        Return the names of currently connected servers.

        Returns:
            server 名称列表。 / A list of server names.
        """
        return [c.cfg.name for c in self._conns]


def get_mcp_manager() -> McpManager:
    """返回容器持有的全局 MCP 管理器（测试可 monkeypatch 本函数）。

    Return the global MCP manager held by the container (tests may monkeypatch this function).
    """
    from core.container import AppContext
    return AppContext.get().mcp_manager()
