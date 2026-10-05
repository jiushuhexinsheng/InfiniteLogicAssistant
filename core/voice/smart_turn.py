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

from typing import Any

from core import config
from core.config import add_reload_hook
from core.logger import logger

_instance: "SmartTurn | None" = None


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
