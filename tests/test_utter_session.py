# -*- coding: utf-8 -*-
"""编排入口续接测试 — /voice/utter 支持 session_id：续接历史会话。
Orchestration entry resumption tests — /voice/utter supports session_id: resuming a history conversation.
"""
import pytest
from fastapi.testclient import TestClient

import server
from core.session.history import HistoryStore


@pytest.fixture
def store(tmp_path):
    return HistoryStore(tmp_path / "history.db")


def _client(monkeypatch, store, captured):
    monkeypatch.setattr("core.session.history.get_history_store", lambda: store)

    async def fake_pipeline(text, session, events, controller, channel=None, messages=None, mode="chat"):
        captured["session_id"] = session.id
        captured["seed"] = messages
        await events.put({"type": "done"})

    async def fake_persist(session, created=None):
        captured["persisted"] = session.id

    monkeypatch.setattr("core.orchestrator.pipeline.run_pipeline", fake_pipeline)
    monkeypatch.setattr("core.api.state.persist", fake_persist)
    return TestClient(server.app)


def _drain(resp):
    for _ in resp.iter_text():
        pass


@pytest.mark.asyncio
async def test_utter_with_session_id_resumes_history(monkeypatch, store):
    """测试携带 session_id 时续接历史会话并注入多轮种子。Tests resuming a history conversation with a session_id and injecting multi-turn seed messages."""
    sid = await store.create_conversation("续接会话")
    await store.save_conversation(sid, [{"role": "user", "content": "上一轮问题"}], status="done", summary="s")

    captured = {}
    client = _client(monkeypatch, store, captured)
    with client.stream("POST", "/api/voice/utter", json={"text": "继续", "session_id": sid}) as r:
        assert r.status_code == 200
        _drain(r)

    # pipeline 收到该会话 id，且历史作为多轮种子
    assert captured["session_id"] == sid
    seed = captured["seed"]
    assert seed and any("上一轮问题" in str(m.get("content")) for m in seed if isinstance(m, dict))
    assert captured["persisted"] == sid


@pytest.mark.asyncio
async def test_utter_without_session_id_creates_new(monkeypatch, store):
    """测试无 session_id 时创建新会话且无历史种子。Tests creating a new conversation without a session_id and with no history seed."""
    captured = {}
    client = _client(monkeypatch, store, captured)
    with client.stream("POST", "/api/voice/utter", json={"text": "你好"}) as r:
        assert r.status_code == 200
        _drain(r)

    assert captured["session_id"]  # 有 session id
    assert captured["seed"] is None  # 无历史种子
    assert captured["persisted"] == captured["session_id"]


@pytest.mark.asyncio
async def test_utter_resume_carries_blocks_in_seed(monkeypatch, store):
    """恢复会话时历史种子含块结构（tool/thinking 块不再丢失）。
    The history seed carries block structure on resume (tool/thinking blocks no
    longer dropped)."""
    tool_blk = {"v": 1, "id": "blk_t", "type": "tool", "ts": "t", "turn_id": "turn_1",
                "agent": "", "meta": {}, "payload": {"name": "run_shell_tool", "output": "ok"}}
    sid = await store.create_conversation("含块会话")
    await store.save_conversation(sid, [
        {"role": "user", "content": "跑个命令", "blocks": [{"type": "text", "payload": {"md": "跑个命令"}}],
         "turn_id": "turn_1", "ts": "2026-09-26T10:00:00"},
        {"role": "assistant", "content": "run_shell_tool: ok", "blocks": [tool_blk],
         "turn_id": "turn_1", "ts": "2026-09-26T10:01:00"},
    ], status="done", summary="s")

    captured = {}
    client = _client(monkeypatch, store, captured)
    with client.stream("POST", "/api/voice/utter", json={"text": "继续", "session_id": sid}) as r:
        assert r.status_code == 200
        _drain(r)

    seed = captured["seed"]
    assistant_seed = next(m for m in seed if m["role"] == "assistant")
    assert assistant_seed["blocks"] == [tool_blk]
    assert assistant_seed["turn_id"] == "turn_1"
    assert assistant_seed["ts"] == "2026-09-26T10:01:00"
