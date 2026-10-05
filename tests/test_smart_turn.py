# -*- coding: utf-8 -*-
"""Smart Turn 包装：禁用/加载失败降级为 True（切段即回合的旧行为）。Smart Turn wrapper degradation."""
import asyncio

from core.voice import smart_turn


def test_disabled_config_degrades(monkeypatch):
    from core import config
    monkeypatch.setattr(config.settings.voice.call, "smart_turn_enabled", False)
    monkeypatch.setattr(smart_turn, "_instance", None)
    st = smart_turn.get_smart_turn()
    assert st.available() is False
    assert asyncio.run(st.is_complete(b"\x00\x01" * 160, 16000)) is True


def test_is_complete_never_raises(monkeypatch):
    """损坏输入也不许抛：返回 True（放行），通话链路不能被轮次模型卡死。"""
    monkeypatch.setattr(smart_turn, "_instance", None)
    st = smart_turn.get_smart_turn()
    assert asyncio.run(st.is_complete(b"", 16000)) in (True, False)


def test_concurrent_is_complete_serialized(monkeypatch):
    """裁决 R12：共享单例分析器的 clear/append→await 分析→clear 临界区必须串行化。

    真实实现 await run_in_executor（ONNX 推理在途可被别的任务插进来 clear/append），
    这里用假分析器在 analyze 中途 sleep 复现同一交错窗口：无锁时先到的调用会读到
    后到调用的缓冲，拿到静默错误的判定；有锁时各调用只看自己那段音频。
    """
    from pipecat.audio.turn.base_turn_analyzer import EndOfTurnState

    PCM_DONE = b"\x01\x00" * 80   # 该段判「说完」
    PCM_NOT = b"\x02\x00" * 80    # 该段判「没说完」

    class FakeAnalyzer:
        """共享缓冲假分析器：缓冲==PCM_DONE 才 COMPLETE；analyze 让出制造交错。"""

        def __init__(self):
            self.sample_rate = 16000
            self._buf = b""

        def clear(self):
            self._buf = b""

        def append_audio(self, buffer, is_speech):
            self._buf += buffer

        async def analyze_end_of_turn(self):
            await asyncio.sleep(0.02)  # 模拟真实 await run_in_executor 的悬空窗口
            state = (
                EndOfTurnState.COMPLETE if self._buf == PCM_DONE else EndOfTurnState.INCOMPLETE
            )
            return state, None

    st = smart_turn.SmartTurn()
    st._loaded = True
    st._analyzer = FakeAnalyzer()
    monkeypatch.setattr(smart_turn, "_instance", st)

    async def run():
        return await asyncio.gather(
            st.is_complete(PCM_DONE, 16000),  # 自己说完 → 应 True
            st.is_complete(PCM_NOT, 16000),   # 没说完 → 应 False
        )

    assert asyncio.run(run()) == [True, False]


def test_analyze_exception_fails_open(monkeypatch):
    """判定途中异常 → 返回 True（放行=旧行为），绝不抛，也不许卡死在锁上。"""

    class BoomAnalyzer:
        sample_rate = 16000

        def clear(self):
            pass

        def append_audio(self, buffer, is_speech):
            pass

        async def analyze_end_of_turn(self):
            raise RuntimeError("judge boom")

    st = smart_turn.SmartTurn()
    st._loaded = True
    st._analyzer = BoomAnalyzer()
    monkeypatch.setattr(smart_turn, "_instance", st)
    assert asyncio.run(st.is_complete(b"\x01\x00" * 80, 16000)) is True
