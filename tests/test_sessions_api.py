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
