# -*- coding: utf-8 -*-
"""Smart Turn v3 包装 — 通话漏斗 L1 的「说完没」复核（本地 ONNX，模型随 pipecat 内置）。

按件采购：只用 pipecat 的 LocalSmartTurnAnalyzerV3 分析器，不引框架。任何不可用
（配置关/包没装/模型坏/输入异常）一律降级 available()=False、is_complete()=True ——
即「浏览器 VAD 切段 = 回合边界」的旧行为，链路不断。

Smart Turn v3 wrapper — the funnel L1 "did they finish" re-check (local ONNX, model
bundled with pipecat). A la carte: only the analyzer, not the framework. Any
unavailable state degrades to available()=False / is_complete()=True — i.e. the legacy
"VAD cut = turn boundary" behaviour; the chain never breaks.
"""
from __future__ import annotations

import asyncio
from typing import Any

from core import config
from core.config import add_reload_hook
from core.logger import logger

_instance: "SmartTurn | None" = None

# 分析器是共享单例，clear/append→await 分析→clear 的临界区必须串行化（裁决 R12）：
# 段 A 的 ONNX 推理在途时 barge-in 触发段 B 上传，会把 A 的缓冲清掉/换掉，两个调用
# 都拿到静默错误的判定。锁按事件循环各配一把、挂在 loop 对象上：asyncio.Lock 会绑定
# 首个争用它的 loop，模块级单把锁跨 loop 复用（测试每次 asyncio.run 都是新 loop）会在
# 争用时报 "bound to a different event loop"；而放模块字典里锁会在争用后反向强引用
# loop，弱键退化成滞留已关闭 loop 的强键。挂 loop 属性则各 loop 各锁、随 loop 一起被
# GC 回收；loop 恒在单线程内跑，创建无竞态。同 loop 内所有并发 is_complete 共用该
# loop 那把锁 → 串行；生产是单一 uvicorn loop，全覆盖。
_LOCK_ATTR = "_smart_turn_lock"


def _lock_for_running_loop() -> asyncio.Lock:
    """取当前事件循环专属的分析锁。Per-event-loop critical-section lock."""
    loop = asyncio.get_running_loop()
    lock = getattr(loop, _LOCK_ATTR, None)
    if lock is None:
        lock = asyncio.Lock()
        setattr(loop, _LOCK_ATTR, lock)
    return lock


class SmartTurn:
    def __init__(self) -> None:
        self._analyzer: Any | None = None
        self._loaded = False

    def _load(self) -> bool:
        if self._loaded:
            return self._analyzer is not None
        self._loaded = True
        try:
            if not config.settings.voice.call.smart_turn_enabled:
                return False
            from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import (
                LocalSmartTurnAnalyzerV3,
            )
            self._analyzer = LocalSmartTurnAnalyzerV3(cpu_count=2)
            self._analyzer.set_sample_rate(16000)
            logger.info("Smart Turn v3 就绪（模型随包内置）")
            return True
        except Exception as e:
            logger.warning("Smart Turn 加载失败，按「切段即回合」降级: {}", e)
            self._analyzer = None
            return False

    def available(self) -> bool:
        return self._load()

    async def is_complete(self, pcm16: bytes, sample_rate: int) -> bool:
        """整段 16-bit PCM → 是否说完。失败/不可用返回 True（放行 = 旧行为）。Never raises."""
        if not self.available() or not pcm16:
            return True
        try:
            # 临界区整体持锁（含 await 分析与前后 clear），并发调用按 loop 串行（R12）。
            async with _lock_for_running_loop():
                a = self._analyzer
                if a is None:
                    return True  # 双保险 / belt and braces
                if sample_rate != a.sample_rate:
                    a.set_sample_rate(sample_rate)
                a.clear()
                a.append_audio(pcm16, True)
                state, _ = await a.analyze_end_of_turn()
                a.clear()
                from pipecat.audio.turn.base_turn_analyzer import EndOfTurnState
                return state == EndOfTurnState.COMPLETE
        except Exception as e:
            logger.warning("Smart Turn 判定失败（放行）: {}", e)
            return True


def get_smart_turn() -> SmartTurn:
    global _instance
    if _instance is None:
        _instance = SmartTurn()
    return _instance


def _reset_smart_turn() -> None:
    global _instance
    _instance = None


add_reload_hook(_reset_smart_turn)
