# -*- coding: utf-8 -*-
"""通话端点：会话生命周期、无会话静默丢、命中/未命中、审计口径。Call endpoints."""
import base64
import io
import json
import time
import wave

import pytest
from fastapi.testclient import TestClient

import server as server_module
import core.config as config_mod
from core.api.voice import call as call_mod


def _wav_bytes(seconds: float = 1.0, amp: int = 8000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        import struct, math
        w.writeframes(b"".join(
            struct.pack("<h", int(amp * math.sin(2 * math.pi * 220 * i / 16000)))
            for i in range(int(16000 * seconds))))
    return buf.getvalue()


class _NoAsr:
    """ASR 桩：不可用 → _cloud_transcribe 直接返回 ""（与 test_server 的 _NoAsr 同语义）。"""
    def available(self):
        return False

    async def transcribe_base64(self, b64, fmt):
        return ""


@pytest.fixture
def client(monkeypatch, tmp_path):
    # 与 tests/test_server.py:39-58 的 client fixture 同口径（隔离 Settings、禁 LLM/ASR
    # 外呼、静态目录与历史库指到 tmp）。额外把 voice.call.smart_turn_enabled 关掉：
    # 否则默认 True 会让端点跑到真 Smart Turn 分析器（假 wav 上结果不确定，测试不可复现）。
    # Smart Turn 本身在 tests/test_smart_turn.py 单独测。
    monkeypatch.setattr(config_mod, "get_settings",
                        lambda: config_mod.Settings(rag=config_mod.RagSection(auto_index=False),
                                                    voice={"call": {"smart_turn_enabled": False}}))
    monkeypatch.setattr(config_mod, "is_llm_configured", lambda: False)
    monkeypatch.setattr(config_mod, "is_asr_configured", lambda: False)
    monkeypatch.setattr("core.voice.get_asr", lambda: _NoAsr())
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>spa</html>", encoding="utf-8")
    monkeypatch.setattr(server_module, "WEB_DIST_DIR", dist)
    monkeypatch.setattr(config_mod, "ROOT_DIR", tmp_path)
    import core.session.history as history_mod
    monkeypatch.setattr(history_mod, "get_history_store",
                        lambda: history_mod.HistoryStore(tmp_path / "history.db"))
    call_mod.reset_session_state()
    yield TestClient(server_module.app)
    call_mod.reset_session_state()


def _seg(client, *, focused=True, in_window=False, wav=None):
    b64 = base64.b64encode(wav or _wav_bytes()).decode()
    return client.post("/api/voice/call/segment",
                       json={"audio_base64": b64, "tab_focused": focused,
                             "in_open_window": in_window})


def test_call_start_stop_lifecycle(client, monkeypatch):
    r = client.post("/api/voice/call/start")
    assert r.status_code == 200 and r.json()["ok"] is True
    assert r.json()["open_window_s"] >= 0
    r2 = client.post("/api/voice/call/stop")
    assert r2.json()["ok"] is True


def test_call_segment_no_session_drops_silently(client):
    """Review Focus #2：无会话（刷新后陈旧前端）→ 200 + hit=False，不 500。"""
    r = _seg(client)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["hit"] is False and body["reason"] == "no_session"


def test_call_segment_hit_and_miss(client, monkeypatch):
    client.post("/api/voice/call/start")
    # 假 L1/L2：本地转写给指令文本，闸门给 command。
    monkeypatch.setattr(call_mod, "_local_transcribe", lambda w: "帮我打开记事本")
    monkeypatch.setattr(call_mod, "_judge", _async_const("command"))
    r = _seg(client)
    assert r.json()["hit"] is True and r.json()["text"] == "帮我打开记事本"

    monkeypatch.setattr(call_mod, "_judge", _async_const("bystander"))
    r2 = _seg(client)
    assert r2.json()["hit"] is False and r2.json()["ok"] is True
    assert r2.json()["reason"] == "bystander"


def test_call_segment_miss_in_open_window_relaxes_after_two(client, monkeypatch):
    """误杀兜底：开放窗口内连续 2 段 miss → 第 3 段 relax=True。"""
    client.post("/api/voice/call/start")
    monkeypatch.setattr(call_mod, "_local_transcribe", lambda w: "……")
    seen = []

    async def judge(t, recent, relax):
        seen.append(relax)
        return "unsure"
    monkeypatch.setattr(call_mod, "_judge", judge)
    for _ in range(3):
        _seg(client, in_window=True)
    assert seen == [False, False, True]


def test_call_segment_audits_upload(client, monkeypatch):
    """Review Focus #5：call 路径云端精转写必须打 audio-upload via= 审计。

    走**真实** `_cloud_transcribe`（只把 core.voice.get_asr 换成可用假件）——钉住的
    是真实接线会打审计行，而不是「打过桩的假件会打审计行」。
    """
    client.post("/api/voice/call/start")
    monkeypatch.setattr(call_mod, "_local_transcribe", None)

    class _FakeAsr:
        def available(self):
            return True
        async def transcribe_base64(self, b64, fmt):
            return "今天天气怎么样"
    monkeypatch.setattr("core.voice.get_asr", lambda: _FakeAsr())

    async def judge(t, r, relax):
        return "command"
    monkeypatch.setattr(call_mod, "_judge", judge)

    from core.logger import audit as real_audit
    calls = []
    monkeypatch.setattr(call_mod, "audit", lambda m: (calls.append(m), real_audit(m))[1])
    r = _seg(client)
    assert r.json()["hit"] is True and r.json()["text"] == "今天天气怎么样"
    assert any(c.startswith("audio-upload via=call-segment") for c in calls)


def test_call_segment_unfocused_dropped_unless_window(client):
    client.post("/api/voice/call/start")
    r = _seg(client, focused=False, in_window=False)
    assert r.json()["hit"] is False and r.json()["reason"] == "unfocused"


def _async_const(v):
    async def f(*a, **k):
        return v
    return f
