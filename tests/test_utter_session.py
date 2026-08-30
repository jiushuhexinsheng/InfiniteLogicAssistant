# -*- coding: utf-8 -*-
"""编排入口续接测试 — /voice/utter 支持 session_id：续接历史会话"""
import pytest
from fastapi.testclient import TestClient

import server
from core.session.history import HistoryStore


@pytest.fixture
def store(tmp_path):
    return HistoryStore(tmp_path / "history.db")


def _client(monkeypatch, store, captured):
    monkeypatch.setattr("core.session.history.get_history_store", lambda: store)

    async def fake_pipeline(text, session, events, controller, channel=None, messages=None):
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
    captured = {}
    client = _client(monkeypatch, store, captured)
    with client.stream("POST", "/api/voice/utter", json={"text": "你好"}) as r:
        assert r.status_code == 200
        _drain(r)

    assert captured["session_id"]  # 有 session id
    assert captured["seed"] is None  # 无历史种子
    assert captured["persisted"] == captured["session_id"]
