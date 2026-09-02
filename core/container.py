# -*- coding: utf-8 -*-
"""应用上下文容器 — 集中管理全局服务实例与生命周期

各模块的 get_xxx() 委托本容器（懒加载持有实例），调用方与测试 mock
（monkeypatch get_xxx）保持不变；server lifespan 经 AppContext.get().start()/shutdown()
统一启动/关闭（scheduler / MCP 子进程 / LLM 连接池）。

Application context container — centralised management of global service instances
and their lifecycle.

Each module's ``get_xxx()`` delegates to this container (lazy-loaded instances);
callers and test mocks (monkeypatch ``get_xxx``) remain unchanged.  Server lifespan
co-ordinates start/shutdown via ``AppContext.get().start()`` / ``.shutdown()``
(scheduler / MCP subprocess / LLM connection pool).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.llm.client import LlmClient
    from core.mcp.manager import McpManager
    from core.memory.facts import FactStore
    from core.scheduler.scheduler import Scheduler
    from core.session.history import HistoryStore
    from core.voice import ASRClient, TTSClient


class AppContext:
    """全局服务容器（进程内单例）。

    Global service container (process-wide singleton).
    """

    _instance: AppContext | None = None

    def __init__(self) -> None:
        """初始化容器，所有服务实例初始为 None（惰性加载）。

        Initialise the container; all service instances start as None (lazy-loaded).
        """
        self._llm: LlmClient | None = None
        self._asr: ASRClient | None = None
        self._tts: TTSClient | None = None
        self._scheduler: Scheduler | None = None
        self._mcp: McpManager | None = None
        self._facts: FactStore | None = None
        self._history: HistoryStore | None = None
        self._started = False

    @classmethod
    def get(cls) -> AppContext:
        """获取进程内唯一的 AppContext 单例。

        Return the process-wide singleton AppContext instance.
        """
        if cls._instance is None:
            cls._instance = AppContext()
        return cls._instance

    # ── getters（懒加载；方法内延迟 import 避免与各模块循环依赖）──

    def llm_client(self) -> LlmClient:
        """获取 LLM 客户端实例（惰性加载）。

        Return the LLM client instance (lazy-loaded).
        """
        if self._llm is None:
            from core.llm.client import LlmClient
            self._llm = LlmClient()
        return self._llm

    def asr(self) -> ASRClient:
        """获取 ASR 语音识别客户端（惰性加载）。

        Return the ASR (speech recognition) client (lazy-loaded).
        """
        if self._asr is None:
            from core.voice import ASRClient
            self._asr = ASRClient()
        return self._asr

    def tts(self) -> TTSClient:
        """获取 TTS 语音合成客户端（惰性加载）。

        Return the TTS (text-to-speech) client (lazy-loaded).
        """
        if self._tts is None:
            from core.voice import TTSClient
            self._tts = TTSClient()
        return self._tts

    def scheduler(self) -> Scheduler:
        """获取定时调度器（惰性加载）。

        Return the scheduler instance (lazy-loaded).
        """
        if self._scheduler is None:
            from core.scheduler.scheduler import Scheduler
            self._scheduler = Scheduler()
        return self._scheduler

    def mcp_manager(self) -> McpManager:
        """获取 MCP 服务器管理器（惰性加载）。

        Return the MCP server manager (lazy-loaded).
        """
        if self._mcp is None:
            from core.mcp.manager import McpManager
            self._mcp = McpManager()
        return self._mcp

    def facts_store(self) -> FactStore:
        """获取事实记忆存储（惰性加载）。

        Return the facts memory store (lazy-loaded).
        """
        if self._facts is None:
            from core.memory.facts import FACTS_DB, FactStore
            self._facts = FactStore(FACTS_DB)
        return self._facts

    def history_store(self) -> HistoryStore:
        """获取会话历史存储（惰性加载）。

        Return the conversation history store (lazy-loaded).
        """
        if self._history is None:
            from core.session.history import HistoryStore
            self._history = HistoryStore()
        return self._history

    # ── 生命周期 ──

    async def start(self) -> None:
        """启动 MCP / 定时调度 / RAG 索引（幂等；对应原 server.py lifespan 启动段）。

        Start MCP / scheduler / RAG indexing (idempotent; corresponds to the
        original server.py lifespan startup segment).
        """
        if self._started:
            return
        from core import config
        from core.logger import logger

        try:
            await self.mcp_manager().start_all()
        except Exception as e:
            logger.warning("MCP 启动失败: {}", e)
        try:
            from core.scheduler.runner import run_scheduled
            sched = self.scheduler()
            sched.set_on_fire(run_scheduled)
            await sched.start()
        except Exception as e:
            logger.warning("定时调度启动失败: {}", e)
        try:
            if config.settings.rag.auto_index:
                from core.rag import maybe_rebuild_index
                await maybe_rebuild_index()
        except Exception as e:
            logger.warning("RAG 索引构建失败: {}", e)
        self._started = True

    async def shutdown(self) -> None:
        """统一关闭：scheduler / MCP 子进程 / LLM 连接池。

        Unified shutdown: scheduler / MCP subprocess / LLM connection pool.
        """
        from core.logger import logger

        self._started = False
        try:
            if self._scheduler is not None:
                await self._scheduler.stop()
        except Exception:
            pass
        try:
            if self._mcp is not None:
                await self._mcp.stop_all()
        except Exception:
            pass
        try:
            if self._llm is not None:
                await self._llm.close()
        except Exception as e:
            logger.warning("LLM 连接池关闭失败: {}", e)

    def reset(self) -> None:
        """清空全部实例（测试隔离 / 完整热重载）。

        Reset all instances to None (test isolation / full hot-reload).
        """
        self._llm = None
        self._asr = None
        self._tts = None
        self._scheduler = None
        self._mcp = None
        self._facts = None
        self._history = None

    def reset_voice(self) -> None:
        """仅重置语音客户端（config 热重载回调用）。

        Reset only the voice clients (called by config hot-reload callback).
        """
        self._asr = None
        self._tts = None
