# -*- coding: utf-8 -*-
"""流式语音 WebSocket 端点：握手、start 校验、partial/final、ASR 不可用报错。

Streaming voice WebSocket endpoint: handshake, start validation, partial/final and the
ASR-unavailable error. Engines are fakes — no model files or network.
"""
from __future__ import annotations

import numpy as np

from core.voice.local.sherpa_onnx import audio


class _VadStream:
    def __init__(self, end_after: int = 3) -> None:
        self.frames: list[np.ndarray] = []
        self.speech = False
        self.end_after = end_after
        self.ended = False

    def accept(self, samples, _sr) -> None:
        self.frames.append(np.asarray(samples, dtype=np.float32))
        self.speech = True

    def speech_detected(self) -> bool:
        return self.speech

    def pop_segment(self):
        if self.ended or len(self.frames) < self.end_after:
            return None
        self.ended = True
        self.speech = False
        return np.concatenate(self.frames)

    def reset(self) -> None:
        self.frames = []
        self.speech = False


class _AsrSession:
    def __init__(self) -> None:
        self.n = 0

    def accept(self, _samples, _sr) -> None:
        self.n += 1

    def decode(self) -> str:
        return "衍衡查天气" if self.n else ""

    def finish(self) -> str:
        return "衍衡查天气" if self.n else ""

    def close(self) -> None:
        pass


class _Runtime:
    def __init__(self, *, asr_ok: bool = True) -> None:
        self.stream = _VadStream()
        self.asr_ok = asr_ok

    def vad(self):
        class V:
            def status(self_inner):
                return True, ""

            def create_stream(self_inner):
                return self.stream
        return V()

    def asr(self):
        ok = self.asr_ok

        class A:
            def status(self_inner):
                return ok, "" if ok else "ASR 模型不存在"

            def create_session(self_inner):
                return _AsrSession()
        return A()

    def kws(self):  # pragma: no cover - kws mode is off in these tests
        class K:
            def status(self_inner):
                return True, ""

            def detect(self_inner, _a, _b):
                return None
        return K()


def _frame() -> bytes:
    return audio.float32_to_pcm16le(np.full(audio.FRAME_SAMPLES, 0.1, dtype=np.float32))


def test_stream_requires_start_json(client):
    """首条消息不是 start JSON → start_required。"""
    with client.websocket_connect("/api/voice/asr/stream") as ws:
        ws.send_bytes(_frame())
        ev = ws.receive_json()
    assert ev["type"] == "error"
    assert ev["code"] == "start_required"


def test_stream_local_partial_then_final(client, monkeypatch):
    """本地模式：ready → speech_start → partial → final（带唤醒判定）。"""
    from core import config
    from core.voice.streaming import session as session_mod

    settings = config.Settings(rag=config.RagSection(auto_index=False))
    settings.voice.asr.mode = "local"
    settings.voice.vad.mode = "local"
    settings.voice.kws.mode = "off"
    settings.voice.wake_word.keywords = ["衍衡"]
    settings.voice.streaming.partial_interval_ms = 0
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    monkeypatch.setattr(session_mod, "get_runtime", lambda: _Runtime())

    with client.websocket_connect("/api/voice/asr/stream") as ws:
        ws.send_json({"type": "start", "sample_rate": 16000})
        assert ws.receive_json()["type"] == "ready"
        for _ in range(3):
            ws.send_bytes(_frame())
        events = []
        while True:
            ev = ws.receive_json()
            events.append(ev)
            if ev["type"] == "final":
                break
        ws.send_json({"type": "stop"})
        assert ws.receive_json()["type"] == "done"

    types = [e["type"] for e in events]
    assert "partial" in types
    final = events[-1]
    assert final["text"] == "衍衡查天气"
    assert final["wake"]["matched"] is True
    assert final["wake"]["command"] == "查天气"


def test_stream_local_asr_unavailable_sends_error(client, monkeypatch):
    """local 模式缺模型 → 明确错误（不静默上云）。"""
    from core import config
    from core.voice.streaming import session as session_mod

    settings = config.Settings(rag=config.RagSection(auto_index=False))
    settings.voice.asr.mode = "local"
    settings.voice.vad.mode = "local"
    settings.voice.kws.mode = "off"
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    monkeypatch.setattr(session_mod, "get_runtime", lambda: _Runtime(asr_ok=False))

    with client.websocket_connect("/api/voice/asr/stream") as ws:
        ws.send_json({"type": "start", "sample_rate": 16000})
        ev = ws.receive_json()
    assert ev["type"] == "error"
    assert ev["code"] == "asr_unavailable"
