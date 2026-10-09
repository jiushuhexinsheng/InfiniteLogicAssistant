# -*- coding: utf-8 -*-
"""会话持久化与会话历史端点。Session persistence and conversation-history endpoints."""
import pytest

import core.config as config_mod
from core.api import state
from core.orchestrator.task import MissingItem, Task


# ─── 会话持久化 ───

@pytest.mark.asyncio
async def test_persist_session_writes_task_json(tmp_path, monkeypatch):
    """测试会话持久化写入任务 JSON 与对话历史。Tests session persistence writing task JSON and conversation history."""
    import json
    import core.session.history as history_mod
    from core.orchestrator.session import Session
    monkeypatch.setattr(config_mod, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(history_mod, "get_history_store",
                        lambda: history_mod.HistoryStore(tmp_path / "history.db"))
    s = Session()
    s.append("user", "你好")
    s.append("assistant", "你好呀")
    s.task = Task("t", "算 1+1", {"a": 1}, [MissingItem(question="x")], "read")
    await state.persist(s, created=1700000000.0)
    p = tmp_path / "data" / "tasks" / f"{s.id}.json"
    assert p.exists()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["session_id"] == s.id
    assert data["task"]["goal"] == "算 1+1"
    assert "finished" in data
    # 完整会话历史也保存（含助手回复）
    conv = await history_mod.HistoryStore(tmp_path / "history.db").get_conversation(s.id)
    assert conv is not None
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]
    assert conv["summary"] == "算 1+1"  # 摘要优先任务目标


# ─── 会话历史 ───

def test_history_endpoints(client, monkeypatch, tmp_path):
    """测试会话历史的列表、详情与删除端点。Tests the history list, detail and delete endpoints."""
    import asyncio
    import core.session.history as history_mod
    store = history_mod.HistoryStore(tmp_path / "h.db")
    monkeypatch.setattr(history_mod, "get_history_store", lambda: store)
    asyncio.run(store.save_conversation(
        "c1", [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}],
        status="done", summary="打招呼"))
    lst = client.get("/api/history").json()
    assert lst["conversations"][0]["id"] == "c1"
    assert lst["conversations"][0]["message_count"] == 2
    det = client.get("/api/history/c1").json()["conversation"]
    assert det["messages"][1]["content"] == "hello"
    assert client.delete("/api/history/c1").json()["ok"] is True
    assert client.get("/api/history/c1").status_code == 404
