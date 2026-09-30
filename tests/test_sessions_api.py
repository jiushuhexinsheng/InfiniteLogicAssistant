# -*- coding: utf-8 -*-
"""会话管理 API 测试 — 新建 / 列表 / 重命名 / 删除。
Session management API tests — create / list / rename / delete.
"""
import pytest
from fastapi.testclient import TestClient

import server
from core.session.history import HistoryStore


@pytest.fixture
def client(tmp_path, monkeypatch):
    store = HistoryStore(tmp_path / "history.db")
    monkeypatch.setattr("core.session.history.get_history_store", lambda: store)
    return TestClient(server.app)


def test_sessions_crud(client):
    """测试会话的完整增删改查流程。Tests the full CRUD flow for sessions."""
    # 新建（默认名）
    r = client.post("/api/sessions").json()
    assert r["ok"]
    sid = r["session"]["id"]
    assert r["session"]["name"] == "新会话"

    # 列表含新建会话
    lst = client.get("/api/sessions").json()["sessions"]
    assert any(s["id"] == sid for s in lst)

    # 重命名
    r = client.patch(f"/api/sessions/{sid}", json={"name": "工作计划"}).json()
    assert r["ok"]
    names = [s["name"] for s in client.get("/api/sessions").json()["sessions"] if s["id"] == sid]
    assert names == ["工作计划"]

    # 删除后不再出现
    assert client.delete(f"/api/sessions/{sid}").json()["ok"] is True
    lst = client.get("/api/sessions").json()["sessions"]
    assert all(s["id"] != sid for s in lst)


def test_sessions_create_with_name(client):
    """测试创建会话时指定名称。Tests creating a session with a given name."""
    r = client.post("/api/sessions", json={"name": "命名会话"}).json()
    assert r["session"]["name"] == "命名会话"


def test_sessions_rename_requires_name(client):
    """测试重命名缺少 name 时返回 400。Tests renaming returning 400 when name is missing."""
    sid = client.post("/api/sessions").json()["session"]["id"]
    resp = client.patch(f"/api/sessions/{sid}", json={})
    assert resp.status_code == 400


# ─── 清除上下文 / 归档 ───


def test_sessions_clear_context_keeps_session(client):
    """测试清除上下文后会话仍保留。Tests sessions remaining after clearing their context."""
    sid = client.post("/api/sessions").json()["session"]["id"]
    r = client.post(f"/api/sessions/{sid}/clear").json()
    assert r["ok"] is True
    # 会话仍存在（未被删除）
    assert any(s["id"] == sid for s in client.get("/api/sessions").json()["sessions"])


def test_sessions_archive_and_filter(client):
    """测试会话的归档与归档过滤。Tests archiving sessions and filtering by archived flag."""
    sid = client.post("/api/sessions").json()["session"]["id"]
    # 默认列表含
    assert any(s["id"] == sid for s in client.get("/api/sessions").json()["sessions"])

    # 归档 → 默认列表排除，?archived=true 可见
    assert client.patch(f"/api/sessions/{sid}", json={"archived": True}).json()["ok"] is True
    assert all(s["id"] != sid for s in client.get("/api/sessions").json()["sessions"])
    arch = client.get("/api/sessions?archived=true").json()["sessions"]
    assert any(s["id"] == sid for s in arch)

    # 取消归档 → 恢复显示
    assert client.patch(f"/api/sessions/{sid}", json={"archived": False}).json()["ok"] is True
    assert any(s["id"] == sid for s in client.get("/api/sessions").json()["sessions"])


# ─── 分叉（docs/designs/07）───


def _msg(role: str, text: str) -> dict:
    return {"role": role, "content": text,
            "blocks": [{"type": "text", "payload": {"md": text}}], "turn_id": "", "ts": "2026-01-01T00:00:00"}


@pytest.mark.asyncio
async def test_sessions_fork_prefix_source_untouched(client):
    """分叉复制前缀为新会话（名字标注来源），源会话只读不动。
    Fork copies the prefix into a new conversation (named after its origin); the source stays read-only."""
    from core.session.history import get_history_store
    store = get_history_store()
    src = await store.create_conversation("源会话")
    await store.save_conversation(src, [_msg("user", "a"), _msg("assistant", "b"), _msg("user", "c")])

    resp = client.post(f"/api/sessions/{src}/fork", json={"up_to": 1})
    assert resp.status_code == 200
    forked = resp.json()["session"]
    assert forked["id"] != src
    assert forked["name"].startswith("分叉自")
    # 响应模型（SessionOut）不带 messages —— 前缀内容经存储核对（前端用本地截断，不读响应消息）。
    # The response model (SessionOut) carries no messages — verify the prefix through the
    # store (the frontend truncates locally and never reads messages off the response).
    forked_conv = await store.get_conversation(forked["id"])
    assert [m["content"] for m in forked_conv["messages"]] == ["a", "b"]

    # 源未动（整段覆盖存储下这是编辑必须先分叉的全部意义）。
    # The source is untouched (the whole point of forking before an edit under
    # whole-overwrite storage).
    src_conv = await store.get_conversation(src)
    assert [m["content"] for m in src_conv["messages"]] == ["a", "b", "c"]


def test_sessions_fork_validation(client):
    """分叉参数校验：up_to 越界 400、缺 up_to 400、源不存在 404。
    Fork validation: up_to out of range → 400, missing up_to → 400, missing source → 404."""
    sid = client.post("/api/sessions").json()["session"]["id"]
    # 空会话：任何 up_to 都越界。Empty session: every up_to is out of range.
    assert client.post(f"/api/sessions/{sid}/fork", json={"up_to": 0}).status_code == 400
    assert client.post(f"/api/sessions/{sid}/fork", json={}).status_code == 400
    assert client.post(f"/api/sessions/{sid}/fork", json={"up_to": "1"}).status_code == 400
    assert client.post("/api/sessions/ghost/fork", json={"up_to": 0}).status_code == 404
