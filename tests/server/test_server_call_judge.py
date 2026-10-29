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


# ─── call_id：每客户端隔离 ───


def test_call_start_generates_id_when_body_without_id(client, monkeypatch):
    """带 body 但没给 call_id → 生成 uuid 并随响应返回，可用它 judge/stop。"""
    call_mod.reset_session_state()

    async def fake_judge(_text, _recent, _relax):
        return "command"

    monkeypatch.setattr(call_mod, "_judge", fake_judge)

    r = client.post("/api/voice/call/start", json={})
    cid = r.json()["call_id"]
    assert len(cid) == 32

    judged = client.post("/api/voice/call/judge", json=_body(call_id=cid)).json()
    assert judged["hit"] is True

    client.post("/api/voice/call/stop", json={"call_id": cid})
    assert client.post("/api/voice/call/judge", json=_body(call_id=cid)).json()["reason"] == "no_session"


def test_call_sessions_are_isolated_by_id(client, monkeypatch):
    """A 的 stop 不影响 B：两个客户端各自命中 / 各自失效。"""
    call_mod.reset_session_state()

    async def fake_judge(_text, _recent, _relax):
        return "command"

    monkeypatch.setattr(call_mod, "_judge", fake_judge)
    client.post("/api/voice/call/start", json={"call_id": "A"})
    client.post("/api/voice/call/start", json={"call_id": "B"})

    assert client.post("/api/voice/call/judge", json=_body(call_id="A")).json()["hit"] is True
    client.post("/api/voice/call/stop", json={"call_id": "A"})

    assert client.post("/api/voice/call/judge", json=_body(call_id="A")).json()["reason"] == "no_session"
    assert client.post("/api/voice/call/judge", json=_body(call_id="B")).json()["hit"] is True
    client.post("/api/voice/call/stop", json={"call_id": "B"})


def test_call_stop_unknown_id_is_noop(client):
    """stop 未知 id：200 成功，不影响其他会话。"""
    call_mod.reset_session_state()
    r = client.post("/api/voice/call/stop", json={"call_id": "nope"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["call_id"] == "nope"


def test_call_session_expires_by_ttl(client, monkeypatch):
    """超过 session_ttl_s 未更新的会话按 no_session 处理。"""
    call_mod.reset_session_state()

    async def fake_judge(_text, _recent, _relax):
        return "command"

    monkeypatch.setattr(call_mod, "_judge", fake_judge)
    client.post("/api/voice/call/start", json={"call_id": "T"})
    ttl = call_mod.config.settings.voice.call.session_ttl_s
    call_mod._sessions["T"].last_segment_at -= ttl + 1

    assert client.post("/api/voice/call/judge", json=_body(call_id="T")).json()["reason"] == "no_session"


def test_call_start_without_body_uses_legacy_key(client):
    """无 body 的旧客户端：使用空串兼容键，响应 call_id 为空。"""
    call_mod.reset_session_state()
    r = client.post("/api/voice/call/start")
    assert r.json()["call_id"] == ""
    assert "" in call_mod._sessions
