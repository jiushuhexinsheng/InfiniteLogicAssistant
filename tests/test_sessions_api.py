# -*- coding: utf-8 -*-
"""会话管理 API 测试 — 新建 / 列表 / 重命名 / 删除"""
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
    r = client.post("/api/sessions", json={"name": "命名会话"}).json()
    assert r["session"]["name"] == "命名会话"


def test_sessions_rename_requires_name(client):
    sid = client.post("/api/sessions").json()["session"]["id"]
    resp = client.patch(f"/api/sessions/{sid}", json={})
    assert resp.status_code == 400
