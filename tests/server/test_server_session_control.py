# -*- coding: utf-8 -*-
"""会话占用守卫、stop 毒丸与任务库管理端点。Session-busy guards, the stop abandon pill and task-library endpoints."""


def test_voice_utter_rejected_while_session_awaiting_answer(client):
    """会话正阻塞在 ask() 时，新的 utter 必须被拒 —— 否则会新建 Session 覆盖注册表，
    把旧的 ask() 变成永久挂死的孤儿。
    A new utter must be rejected while the session is blocked in ask(); otherwise it would
    create a fresh Session, overwrite the registry, and orphan the old ask() forever."""
    import asyncio
    from core.api import state
    from core.orchestrator.control import StopController
    from core.orchestrator.pipeline import EventQueueChannel
    from core.orchestrator.session import Session

    session = Session(session_id="busy")
    ch = EventQueueChannel(asyncio.Queue(), "busy")
    ch.awaiting_answer = True
    session.channel = ch
    state.register(session, StopController())
    try:
        r = client.post("/api/voice/utter", json={"text": "新的指令", "session_id": "busy"})
        assert r.status_code == 409
        assert "等待回答" in r.json()["error"]
    finally:
        state.cleanup("busy")


def test_voice_utter_allowed_when_session_not_awaiting(client):
    """会话未在等回答时正常放行（回归：守卫不能误伤正常续接）。
    A session that is not awaiting an answer proceeds normally (the guard must not block
    ordinary resumption)."""
    import asyncio
    from core.api import state
    from core.orchestrator.control import StopController
    from core.orchestrator.pipeline import EventQueueChannel
    from core.orchestrator.session import Session

    session = Session(session_id="idle-sess")
    ch = EventQueueChannel(asyncio.Queue(), "idle-sess")
    ch.awaiting_answer = False
    session.channel = ch
    state.register(session, StopController())
    try:
        r = client.post("/api/voice/utter", json={"text": "新的指令", "session_id": "idle-sess"})
        assert r.status_code == 200   # 返回 SSE 流
    finally:
        state.cleanup("idle-sess")


def test_task_stop_abandons_pending_answer(client):
    """POST /task/{sid}/stop 顺带向通道投弃题毒丸，解除阻塞的 ask —— 否则会话永久
    占用，新指令全撞 utter 409。
    The stop endpoint also delivers the abandon pill to the channel, unblocking a
    pending ask; otherwise the session stays busy forever and every follow-up utter
    hits 409."""
    import asyncio
    from core.api import state
    from core.orchestrator.control import StopController
    from core.orchestrator.pipeline import EventQueueChannel
    from core.orchestrator.session import ABANDON_REASON, Answer, Session

    session = Session(session_id="stop-abandon")
    ch = EventQueueChannel(asyncio.Queue(), "stop-abandon")
    ch.awaiting_answer = True
    session.channel = ch
    ctrl = StopController()
    state.register(session, ctrl)
    try:
        r = client.post("/api/task/stop-abandon/stop")
        assert r.status_code == 200
        assert ctrl.token.is_cancelled  # 原有停止行为保持
        ans = ch.answers.get_nowait()   # 毒丸已入队 → ask() 得以解除
        assert ans == Answer(text="", choice=None, reason=ABANDON_REASON)
    finally:
        state.cleanup("stop-abandon")


def test_library_list_and_delete(client, tmp_path, monkeypatch):
    """任务库列表与删除端点。The task-library list and delete endpoints."""
    import asyncio

    from core.orchestrator.task import Task
    from core.tasks import store as store_mod

    st = store_mod.TaskStore(tmp_path / "lib.sqlite")
    import core.api.library as lib
    monkeypatch.setattr(lib, "_get_store", lambda: st)

    r = client.get("/api/library")
    assert r.status_code == 200
    assert r.json()["tasks"] == []

    asyncio.run(st.record(Task("t", "复制文件", {"dest": "下载"}, risk="read"),
                          {"status": "done", "steps": []}, session_id="s1"))

    tasks = client.get("/api/library").json()["tasks"]
    assert len(tasks) == 1 and tasks[0]["goal"] == "复制文件"

    tid = tasks[0]["id"]
    assert client.get(f"/api/library/{tid}").json()["task"]["params"] == {"dest": "下载"}
    assert client.delete(f"/api/library/{tid}").status_code == 200
    assert client.get("/api/library").json()["tasks"] == []


def test_library_detail_unknown_404(client, tmp_path, monkeypatch):
    """未知任务 id 返回 404。An unknown task id returns 404."""
    from core.tasks import store as store_mod
    import core.api.library as lib
    monkeypatch.setattr(lib, "_get_store", lambda: store_mod.TaskStore(tmp_path / "lib2.sqlite"))
    assert client.get("/api/library/999999").status_code == 404
