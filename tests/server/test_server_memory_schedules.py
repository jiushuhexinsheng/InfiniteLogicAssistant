# -*- coding: utf-8 -*-
"""记忆事实与定时任务端点。Memory facts and scheduled-task endpoints."""


def test_memory_endpoint(client):
    """测试 /api/memory 返回记忆事实。Tests /api/memory returning memory facts."""
    resp = client.get("/api/memory")
    assert resp.status_code == 200
    assert "facts" in resp.json()


def test_schedules_endpoints(client, tmp_path, monkeypatch):
    """测试定时任务的增删查端点。Tests the scheduled task create, list and delete endpoints."""
    import core.scheduler.scheduler as sched_mod
    from core.scheduler.scheduler import Scheduler
    monkeypatch.setattr(sched_mod, "get_scheduler", lambda: Scheduler(path=tmp_path / "sched.json"))
    assert client.get("/api/schedules").json()["schedules"] == []
    r = client.post("/api/schedules", json={"cron": "0 9 * * *", "prompt": "查天气"})
    assert r.status_code == 200
    sid = r.json()["schedule"]["id"]
    assert len(client.get("/api/schedules").json()["schedules"]) == 1
    assert client.delete(f"/api/schedules/{sid}").status_code == 200
    assert client.get("/api/schedules").json()["schedules"] == []
