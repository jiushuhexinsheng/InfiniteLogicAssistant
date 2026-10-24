# -*- coding: utf-8 -*-
"""流式会话单测：VAD 分段、partial、final、唤醒判定与不可用报错。

Streaming-session tests: VAD segmentation, partials, finals, wake verdict and
unavailable-model errors. All engines are fakes — no model files or network.
"""
from __future__ import annotations

import numpy as np
import pytest

from core import config
from core.voice.local.sherpa_onnx import audio
from core.voice.streaming import SessionError
from core.voice.streaming.session import StreamingSession


class FakeWS:
    """最小 WebSocket 桩。Minimal WebSocket stub."""

    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.closed = False

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)

    async def close(self, code: int = 1000) -> None:
        self.closed = True


class FakeVadStream:
    """按帧数结束一段的 VAD 桩。VAD stub that ends a segment after N frames."""

    def __init__(self, end_after: int = 3) -> None:
        self.accepted: list[np.ndarray] = []
        self.speech = False
        self.end_after = end_after
        self.ended = False

    def accept(self, samples: np.ndarray, _sr: int) -> None:
        self.accepted.append(np.asarray(samples, dtype=np.float32))
        self.speech = True

    def speech_detected(self) -> bool:
        return self.speech

    def pop_segment(self) -> np.ndarray | None:
        if self.ended or len(self.accepted) < self.end_after:
            return None
        self.ended = True
        self.speech = False
        return np.concatenate(self.accepted)

    def reset(self) -> None:
        self.accepted = []
        self.speech = False


class FakeAsrSession:
    """固定返回文本的 ASR 会话桩。ASR-session stub returning a fixed text."""

    def __init__(self) -> None:
        self.accepted = 0
        self.closed = False

    def accept(self, _samples: np.ndarray, _sr: int) -> None:
        self.accepted += 1

    def decode(self) -> str:
        return "衍衡查天气" if self.accepted else ""

    def finish(self) -> str:
        return "衍衡查天气" if self.accepted else ""

    def close(self) -> None:
        self.closed = True


class FakeAsrEngine:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok

    def status(self) -> tuple[bool, str]:
        return self.ok, "" if self.ok else "ASR 模型不存在"

    def create_session(self) -> FakeAsrSession:
        return FakeAsrSession()


class FakeKwsEngine:
    def status(self) -> tuple[bool, str]:
        return True, ""

    def detect(self, _samples: np.ndarray, _sr: int) -> str | None:
        return "衍衡"


class FakeVadEngine:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.stream = FakeVadStream()

    def status(self) -> tuple[bool, str]:
        return self.ok, "" if self.ok else "VAD 模型不存在"

    def create_stream(self) -> FakeVadStream:
        return self.stream


class FakeRuntime:
    def __init__(self, *, vad_ok: bool = True, asr_ok: bool = True) -> None:
        self._vad = FakeVadEngine(vad_ok)
        self._asr = FakeAsrEngine(asr_ok)
        self._kws = FakeKwsEngine()

    def vad(self):
        return self._vad

    def asr(self):
        return self._asr

    def kws(self):
        return self._kws


def _pin(monkeypatch, *, mode: str = "local", kws_mode: str = "local") -> None:
    """钉住会话读取的配置。Pin the config the session reads."""
    monkeypatch.setattr(config.settings.voice.asr, "mode", mode)
    monkeypatch.setattr(config.settings.voice.asr, "streaming", True)
    monkeypatch.setattr(config.settings.voice.vad, "mode", "local")
    monkeypatch.setattr(config.settings.voice.kws, "mode", kws_mode)
    monkeypatch.setattr(config.settings.voice.wake_word, "keywords", ["衍衡"])
    monkeypatch.setattr(config.settings.voice.streaming, "partial_interval_ms", 0)


def _frame(value: float = 0.1) -> bytes:
    return audio.float32_to_pcm16le(np.full(audio.FRAME_SAMPLES, value, dtype=np.float32))


@pytest.mark.asyncio
async def test_local_session_partial_then_final_with_wake(monkeypatch):
    """本地模式：先 partial，段尾 final 带唤醒判定。Local: partial then final+wake."""
    _pin(monkeypatch)
    ws = FakeWS()
    session = StreamingSession(ws, {"type": "start"}, runtime=FakeRuntime())
    await session.start_session()
    assert ws.sent[0]["type"] == "ready"
    assert ws.sent[0]["mode"] == "local"

    await session._on_audio(_frame())
    await session._on_audio(_frame())
    assert any(m["type"] == "partial" and m["text"] for m in ws.sent)

    await session._on_audio(_frame())
    finals = [m for m in ws.sent if m["type"] == "final"]
    assert len(finals) == 1
    assert finals[0]["text"] == "衍衡查天气"
    assert finals[0]["engine"] == "local"
    assert finals[0]["wake"]["matched"] is True
    assert finals[0]["wake"]["command"] == "查天气"


@pytest.mark.asyncio
async def test_local_mode_requires_local_asr(monkeypatch):
    """local 模式本地 ASR 不可用 → 明确报错，不静默上云。Local mode fails loudly."""
    _pin(monkeypatch, mode="local")
    session = StreamingSession(FakeWS(), {"type": "start"}, runtime=FakeRuntime(asr_ok=False))
    with pytest.raises(SessionError) as e:
        await session.start_session()
    assert e.value.code == "asr_unavailable"


@pytest.mark.asyncio
async def test_mute_discards_pre_roll_and_active_segment(monkeypatch):
    """mute/unmute 必须清空预卷并重置 VAD/段状态：否则播报结束后第一段会混入
    播报前的旧音频（回声护栏漏音）。
    mute/unmute must clear the pre-roll and reset VAD/segment state; otherwise the
    first segment after playback carries pre-playback audio (echo-guard leak)."""
    import json

    _pin(monkeypatch)
    runtime = FakeRuntime()
    session = StreamingSession(FakeWS(), {"type": "start"}, runtime=runtime)
    await session.start_session()
    await session._on_audio(_frame())          # 触发 speech_start。Starts a segment.
    assert session._active is True
    # 模拟预卷里还有残留帧（真实链路中播报前会累积 ~200ms）。Simulate leftover pre-roll.
    session._pre_roll.append(np.zeros(audio.FRAME_SAMPLES, dtype=np.float32))

    await session._on_control(json.dumps({"type": "mute"}))
    assert session._active is False
    assert len(session._pre_roll) == 0
    assert runtime._vad.stream.accepted == []   # VAD 已重置。VAD reset.
    assert session._frames == []

    await session._on_audio(_frame())           # 播报期帧被丢弃。Frames dropped while muted.
    assert len(session._pre_roll) == 0

    await session._on_control(json.dumps({"type": "unmute"}))
    assert len(session._pre_roll) == 0
    assert runtime._vad.stream.accepted == []


@pytest.mark.asyncio
async def test_vad_unavailable_fails(monkeypatch):
    """VAD 模型不可用 → 会话拒绝启动（本项目没有云端 VAD 兜底）。"""
    _pin(monkeypatch)
    session = StreamingSession(FakeWS(), {"type": "start"}, runtime=FakeRuntime(vad_ok=False))
    with pytest.raises(SessionError) as e:
        await session.start_session()
    assert e.value.code == "vad_unavailable"


@pytest.mark.asyncio
async def test_cloud_mode_uses_cloud_and_no_partial(monkeypatch):
    """cloud 模式：没有 partial，段尾走云端 final。Cloud mode: no partials, cloud final."""
    _pin(monkeypatch, mode="cloud", kws_mode="api")

    async def fake_cloud(_self, _segment):
        return "打开浏览器"

    # start_session 会检查云端 ASR 是否可用（get_asr().available()）；本地 config.yaml 里
    # 配了 ASR 时该检查为真，但 CI 从 example 新建的 config 未配 → 需要桩掉。
    # start_session checks cloud ASR availability (get_asr().available()); it is True with a
    # configured local config.yaml but False in CI's fresh example config, so stub it.
    import core.voice as voice_mod

    class _CloudAsr:
        def available(self) -> bool:
            return True

    monkeypatch.setattr(voice_mod, "get_asr", lambda: _CloudAsr())
    monkeypatch.setattr(StreamingSession, "_cloud_transcribe", fake_cloud)
    ws = FakeWS()
    session = StreamingSession(ws, {"type": "start"}, runtime=FakeRuntime())
    await session.start_session()
    for _ in range(3):
        await session._on_audio(_frame())
    assert not any(m["type"] == "partial" for m in ws.sent)
    finals = [m for m in ws.sent if m["type"] == "final"]
    assert len(finals) == 1
    assert finals[0]["engine"] == "cloud"
    assert finals[0]["text"] == "打开浏览器"
    assert finals[0]["wake"]["matched"] is False
