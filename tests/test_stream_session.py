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
    """按帧数结束一段的 VAD 桩；可模拟触发滞后。VAD stub that ends a segment after N frames."""

    def __init__(self, end_after: int = 3, trigger_after: int = 1) -> None:
        self.accepted: list[np.ndarray] = []
        self.speech = False
        self.end_after = end_after
        self.trigger_after = trigger_after
        self.ended = False

    def accept(self, samples: np.ndarray, _sr: int) -> None:
        self.accepted.append(np.asarray(samples, dtype=np.float32))
        if len(self.accepted) >= self.trigger_after:
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

    def __init__(self, text: str = "衍衡查天气") -> None:
        self.text = text
        self.accepted = 0
        self.closed = False

    def accept(self, _samples: np.ndarray, _sr: int) -> None:
        self.accepted += 1

    def decode(self) -> str:
        return self.text if self.accepted else ""

    def finish(self) -> str:
        return self.text if self.accepted else ""

    def close(self) -> None:
        self.closed = True


class FakeAsrEngine:
    def __init__(self, ok: bool = True, text: str = "衍衡查天气") -> None:
        self.ok = ok
        self.text = text
        self.sessions: list[FakeAsrSession] = []

    def status(self) -> tuple[bool, str]:
        return self.ok, "" if self.ok else "ASR 模型不存在"

    def create_session(self) -> FakeAsrSession:
        session = FakeAsrSession(self.text)
        self.sessions.append(session)
        return session


class FakeKwsEngine:
    def __init__(self, hit: str | None = "衍衡") -> None:
        self.hit = hit

    def status(self) -> tuple[bool, str]:
        return True, ""

    def detect(self, _samples: np.ndarray, _sr: int) -> str | None:
        return self.hit


class FakeVadEngine:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.stream = FakeVadStream()

    def status(self) -> tuple[bool, str]:
        return self.ok, "" if self.ok else "VAD 模型不存在"

    def create_stream(self) -> FakeVadStream:
        return self.stream


class FakeRuntime:
    def __init__(self, *, vad_ok: bool = True, asr_ok: bool = True,
                 asr_text: str = "衍衡查天气", kws_hit: str | None = "衍衡") -> None:
        self._vad = FakeVadEngine(vad_ok)
        self._asr = FakeAsrEngine(asr_ok, asr_text)
        self._kws = FakeKwsEngine(kws_hit)

    def vad(self):
        return self._vad

    def asr(self):
        return self._asr

    def kws(self):
        return self._kws


def _pin(monkeypatch, *, mode: str = "local", kws_mode: str = "local",
         wake_enabled: bool = True, kws_enabled: bool = True,
         asr_streaming: bool = True, upload_preroll: bool = True) -> None:
    """钉住会话读取的配置。Pin the config the session reads."""
    monkeypatch.setattr(config.settings.voice.asr, "mode", mode)
    monkeypatch.setattr(config.settings.voice.asr, "streaming", asr_streaming)
    monkeypatch.setattr(config.settings.voice.vad, "mode", "local")
    monkeypatch.setattr(config.settings.voice.kws, "mode", kws_mode)
    monkeypatch.setattr(config.settings.voice.kws, "enabled", kws_enabled)
    monkeypatch.setattr(config.settings.voice.kws, "upload_preroll", upload_preroll)
    monkeypatch.setattr(config.settings.voice.wake_word, "enabled", wake_enabled)
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
async def test_pre_roll_covers_vad_trigger_lag(monkeypatch):
    """VAD 触发滞后时不吞首字：触发前收到的帧必须全部喂给 ASR。

    TEN-VAD 的 speech_detected 比真实语音起点晚 250–500 ms；预卷短于这个滞后会把
    「衍衡」这类短词的首字切掉。这里让 VAD 到第 30 帧才报 speech，断言 ASR 收到了
    触发前的 29 帧预卷（旧实现 maxlen=10 会丢首字）。

    When the VAD triggers late, every frame received before the trigger must reach the
    ASR stream; otherwise the first syllable of a short word is clipped. The fake VAD
    only reports speech at frame 30, so frames 1–29 must arrive via the pre-roll (the
    old maxlen=10 would clip them).
    """
    _pin(monkeypatch)
    runtime = FakeRuntime()
    runtime._vad.stream = FakeVadStream(end_after=40, trigger_after=30)
    ws = FakeWS()
    session = StreamingSession(ws, {"type": "start"}, runtime=runtime)
    await session.start_session()

    for _ in range(40):
        await session._on_audio(_frame())

    assert [m for m in ws.sent if m["type"] == "final"]
    assert runtime._asr.sessions[0].accepted == 40   # 30 帧预卷 + 触发后 10 帧


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
    # 模拟预卷里还有残留帧（真实链路中播报前会累积预卷）。Simulate leftover pre-roll.
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


# ─── hybrid：疑似截断的云端兜底 ───


def test_looks_truncated_boundaries():
    """2 字/秒的保守阈值边界。The conservative 2 chars/s threshold boundaries."""
    from core.voice.streaming.session import _looks_truncated

    assert _looks_truncated("好", 0.49) is False       # 短于 0.5s 不判
    assert _looks_truncated("好", 0.5) is False        # 1 < 1.0 不成立（严格小于）
    assert _looks_truncated("好", 0.51) is True        # 1 < 1.02
    assert _looks_truncated("好", 1.46) is True        # 1 < 2.92
    assert _looks_truncated("你好", 1.0) is False      # 2 < 2.0 不成立
    assert _looks_truncated("你好", 1.46) is True      # 2 < 2.92


async def _run_hybrid(monkeypatch, *, local_text: str, frames: int,
                      cloud_text: str = "你好眼横", cloud_raises: bool = False):
    """跑一段 hybrid 会话，返回 (final 事件, 云端调用次数)。Run one hybrid segment."""
    _pin(monkeypatch, mode="hybrid")
    runtime = FakeRuntime(asr_text=local_text)
    runtime._vad.stream = FakeVadStream(end_after=frames, trigger_after=1)
    cloud_calls: list[int] = []

    async def fake_cloud(_self, segment):
        cloud_calls.append(int(segment.size))
        if cloud_raises:
            raise RuntimeError("cloud down")
        return cloud_text

    monkeypatch.setattr(StreamingSession, "_cloud_transcribe", fake_cloud)
    ws = FakeWS()
    session = StreamingSession(ws, {"type": "start"}, runtime=runtime)
    await session.start_session()
    for _ in range(frames):
        await session._on_audio(_frame())
    finals = [m for m in ws.sent if m["type"] == "final"]
    assert finals, "段应产生 final"
    return finals[-1], cloud_calls


@pytest.mark.asyncio
async def test_hybrid_truncated_short_text_falls_back(monkeypatch):
    """1.46s 只转出 1 个字 → 疑似截断，走云端兜底并采用云端文本。"""
    final, calls = await _run_hybrid(monkeypatch, local_text="好", frames=73)
    assert calls, "疑似截断应触发云端兜底"
    assert final["engine"] == "cloud"
    assert final["fallback"] is True
    assert final["text"] == "你好眼横"


@pytest.mark.asyncio
async def test_hybrid_short_segment_still_falls_back(monkeypatch):
    """0.6s 只转出 1 个字（1 < 1.2）→ 仍判截断。"""
    final, calls = await _run_hybrid(monkeypatch, local_text="好", frames=30)
    assert calls
    assert final["engine"] == "cloud"


@pytest.mark.asyncio
async def test_hybrid_very_short_utterance_stays_local(monkeypatch):
    """0.4s 的「好」是真实短句（未达 0.5s 门槛）→ 不上云。"""
    final, calls = await _run_hybrid(monkeypatch, local_text="好", frames=20)
    assert calls == []
    assert final["engine"] == "local"
    assert final["fallback"] is False
    assert final["text"] == "好"


@pytest.mark.asyncio
async def test_hybrid_normal_length_text_stays_local(monkeypatch):
    """1.46s 的正常长度转写（13 字）→ 不兜底。"""
    final, calls = await _run_hybrid(
        monkeypatch, local_text="这是一段正常长度的转写结果", frames=73
    )
    assert calls == []
    assert final["engine"] == "local"


@pytest.mark.asyncio
async def test_hybrid_empty_text_falls_back(monkeypatch):
    """本地空文本仍走云端（回归保护）。Empty local text still falls back."""
    final, calls = await _run_hybrid(monkeypatch, local_text="", frames=73)
    assert calls
    assert final["engine"] == "cloud"
    assert final["text"] == "你好眼横"


@pytest.mark.asyncio
async def test_hybrid_cloud_failure_keeps_local_text(monkeypatch):
    """云端兜底抛错：保留本地短文本，不崩、不覆盖成空串。"""
    final, calls = await _run_hybrid(
        monkeypatch, local_text="好", frames=73, cloud_raises=True
    )
    assert calls
    assert final["engine"] == "local"
    assert final["fallback"] is False
    assert final["text"] == "好"


# ─── 唤醒闸门（gate）───


def _stub_cloud(monkeypatch) -> None:
    """让 start_session 的云端可用性检查通过。Make the cloud availability check pass."""
    import core.voice as voice_mod

    class _CloudAsr:
        def available(self) -> bool:
            return True

    monkeypatch.setattr(voice_mod, "get_asr", lambda: _CloudAsr())


async def _run_cloud_segment(monkeypatch, *, kws_hit: str | None,
                             gate: str | None = None, mode: str = "cloud"):
    """跑一段 cloud 模式会话，返回 (final, 云端调用列表, ws, session)。"""
    _pin(monkeypatch, mode=mode, kws_mode="local")
    _stub_cloud(monkeypatch)
    runtime = FakeRuntime(kws_hit=kws_hit)
    runtime._vad.stream = FakeVadStream(end_after=3)
    calls: list[int] = []

    async def fake_cloud(_self, segment):
        calls.append(int(segment.size))
        return "打开浏览器"

    monkeypatch.setattr(StreamingSession, "_cloud_transcribe", fake_cloud)
    ws = FakeWS()
    session = StreamingSession(ws, {"type": "start"}, runtime=runtime)
    await session.start_session()
    if gate is not None:
        import json
        await session._on_control(json.dumps({"type": "gate", "mode": gate}))
    for _ in range(3):
        await session._on_audio(_frame())
    finals = [m for m in ws.sent if m["type"] == "final"]
    assert finals, "段应产生 final"
    return finals[-1], calls, ws, session


@pytest.mark.asyncio
async def test_gate_wake_kws_miss_drops_before_cloud(monkeypatch):
    """gate=wake 且 KWS 未命中：不上云、final 标记 drop。"""
    final, calls, _ws, _session = await _run_cloud_segment(monkeypatch, kws_hit=None)
    assert calls == [], "闸门未命中不得调用云端 ASR"
    assert final["gate"] == "drop"
    assert final["text"] == ""
    assert final["engine"] == "kws"
    assert final["wake"]["matched"] is False


@pytest.mark.asyncio
async def test_gate_wake_kws_hit_uploads(monkeypatch):
    """gate=wake 且 KWS 命中：正常上云，final 带唤醒结论。"""
    final, calls, _ws, _session = await _run_cloud_segment(monkeypatch, kws_hit="衍衡")
    assert calls, "闸门命中应上传云端"
    assert final["gate"] == "wake"
    assert final["text"] == "打开浏览器"
    assert final["wake"]["matched"] is True
    assert final["wake"]["source"] == "kws"


@pytest.mark.asyncio
async def test_gate_open_uploads_on_kws_miss(monkeypatch):
    """gate=open（通话/续聊/作答）：KWS 未命中也不得上传拦截。"""
    final, calls, _ws, _session = await _run_cloud_segment(
        monkeypatch, kws_hit=None, gate="open"
    )
    assert calls, "开放聆听必须照常上云"
    assert final["gate"] == "open"
    assert final["text"] == "打开浏览器"
    assert any(m.get("type") == "gate" and m.get("mode") == "open"
               for m in _ws.sent)


@pytest.mark.asyncio
async def test_gate_capable_false_clamps_wake_to_open(monkeypatch):
    """kws.mode=api（无本地闸门）时 wake 请求被夹回 open，并回 ack。"""
    _pin(monkeypatch, mode="local", kws_mode="api")
    ws = FakeWS()
    session = StreamingSession(ws, {"type": "start"}, runtime=FakeRuntime())
    await session.start_session()
    ready = ws.sent[0]
    assert ready["gate_capable"] is False
    assert ready["gate_default"] == "open"

    import json
    await session._on_control(json.dumps({"type": "gate", "mode": "wake"}))
    ack = [m for m in ws.sent if m["type"] == "gate"][-1]
    assert ack["mode"] == "open"


@pytest.mark.asyncio
async def test_wake_disabled_rejects_session(monkeypatch):
    """wake_word.enabled=false：拒绝建立语音流（只用文字）。"""
    _pin(monkeypatch, wake_enabled=False)
    session = StreamingSession(FakeWS(), {"type": "start"}, runtime=FakeRuntime())
    with pytest.raises(SessionError) as e:
        await session.start_session()
    assert e.value.code == "wake_disabled"


@pytest.mark.asyncio
async def test_kws_mode_off_treats_all_speech_as_command(monkeypatch):
    """kws.mode=off：不判唤醒，整句都是指令。"""
    _pin(monkeypatch, mode="local", kws_mode="off")
    runtime = FakeRuntime(asr_text="打开浏览器")
    runtime._vad.stream = FakeVadStream(end_after=3)
    ws = FakeWS()
    session = StreamingSession(ws, {"type": "start"}, runtime=runtime)
    await session.start_session()
    for _ in range(3):
        await session._on_audio(_frame())
    final = [m for m in ws.sent if m["type"] == "final"][-1]
    assert final["wake"]["matched"] is True
    assert final["wake"]["command"] == "打开浏览器"
    assert final["wake"]["source"] == "off"


@pytest.mark.asyncio
async def test_asr_streaming_false_sends_no_partial(monkeypatch):
    """voice.asr.streaming=false：不再推 partial，但段尾仍有 final。"""
    _pin(monkeypatch, mode="local", asr_streaming=False)
    runtime = FakeRuntime()
    runtime._vad.stream = FakeVadStream(end_after=3)
    ws = FakeWS()
    session = StreamingSession(ws, {"type": "start"}, runtime=runtime)
    await session.start_session()
    for _ in range(3):
        await session._on_audio(_frame())
    assert not any(m["type"] == "partial" for m in ws.sent)
    assert any(m["type"] == "final" for m in ws.sent)
