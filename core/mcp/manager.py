# -*- coding: utf-8 -*-
"""MCP 生命周期管理 — 启动/停止全部 MCP server，并把工具注册进 TOOLS"""
from core import config
from core.logger import logger
from core.mcp.client import McpConnection, McpServerCfg
from core.tools.mcp_bridge import register_mcp_tools, unregister_mcp_tools


class McpManager:
    def __init__(self) -> None:
        self._conns: list[McpConnection] = []

    async def start_all(self) -> None:
        for s in config.settings.mcp.servers:
            c = McpConnection(McpServerCfg(s.name, s.command, s.args))
            try:
                await c.connect()
                await register_mcp_tools(c)
                self._conns.append(c)
            except Exception as e:
                logger.warning("MCP server '{}' 连接失败: {}", s.name, e)

    async def stop_all(self) -> None:
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
        return [c.cfg.name for c in self._conns]


def get_mcp_manager() -> McpManager:
    """返回容器持有的全局 MCP 管理器（测试可 monkeypatch 本函数）。"""
    from core.container import AppContext
    return AppContext.get().mcp_manager()
