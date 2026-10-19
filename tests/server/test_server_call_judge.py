# -*- coding: utf-8 -*-
"""通话纯文本判定端点：会话生命周期 + L0/L1/L2 文本路径。

Text-only call judging: session lifecycle plus the L0/L1/L2 text path.
"""
from __future__ import annotations

from core.api.voice import call as call_mod


def _body(text: str = "帮我打开记事本", **over):
    body = {"text": text, "duration_ms": 2000, "rms": 0.1,
            "tab_focused": True, "in_open_window": False}
    body.update(over)
    return body


def test_call_judge_requires_session(client):
    call_mod.reset_session_state()
    r = client.post("/api/voice/call/judge", json=_body())
    assert r.json()["ok"] is True
    assert r.json()["hit"] is False
    assert r.json()["reason"] == "no_session"


def test_call_judge_hit_and_stop(client, monkeypatch):
    call_mod.reset_session_state()
    client.post("/api/voice/call/start")

    async def fake_judge(_text, _recent, _relax):
        return "command"

    monkeypatch.setattr(call_mod, "_judge", fake_judge)
    r = client.post("/api/voice/call/judge", json=_body())
    data = r.json()
    assert data["ok"] is True and data["hit"] is True
    assert data["text"] == "帮我打开记事本"
    assert data["stage"] == "l2"
    assert data["reason"] == "command"

    client.post("/api/voice/call/stop")
    r2 = client.post("/api/voice/call/judge", json=_body())
    assert r2.json()["reason"] == "no_session"


def test_call_judge_quick_screen_filler(client, monkeypatch):
    call_mod.reset_session_state()
    client.post("/api/voice/call/start")

    async def boom(*_a, **_k):
        raise AssertionError("filler 不该走到 L2")

    monkeypatch.setattr(call_mod, "_judge", boom)
    r = client.post("/api/voice/call/judge", json=_body("嗯"))
    data = r.json()
    assert data["hit"] is False
    assert data["stage"] == "l1"
    assert data["reason"] == "filler"
    client.post("/api/voice/call/stop")
