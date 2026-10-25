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


def test_voice_utter_rejects_unsafe_session_id(client):
    """session_id 会拼进 data/tasks/<id>.json 的写路径，必须拒绝路径分隔符等字符，
    否则 ../ 可越界写文件。
    session_id is spliced into the write path data/tasks/<id>.json, so path separators
    and similar characters must be rejected — otherwise ../ writes outside the directory."""
    r = client.post("/api/voice/utter", json={"text": "新的指令", "session_id": "../../escape"})
    assert r.status_code == 400
    assert "session_id" in r.json()["error"]


def test_voice_utter_accepts_safe_session_id(client):
    """正常 id（uuid hex / 字母数字连字符）不受净化误伤。
    Normal ids (uuid hex / alphanumerics and hyphens) are not rejected by sanitisation."""
    from core.api import state

    try:
        r = client.post("/api/voice/utter",
                        json={"text": "新的指令", "session_id": "a1b2c3d4e5f6-ok"})
        assert r.status_code == 200
    finally:
        state.cleanup("a1b2c3d4e5f6-ok")


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


def test_stop_releases_paused_run(client):
    """暂停中的 run 被 stop 时必须一并恢复暂停闸门 —— 否则执行循环阻塞在
    wait_if_paused()，取消令牌永远没人检查，stop 形同虚设。
    Stopping a paused run must also release the pause gate — otherwise the execution
    loop stays blocked in wait_if_paused(), the cancel token is never checked, and
    stop is a no-op."""
    import asyncio
    from core.api import state
    from core.orchestrator.control import PauseController, PauseMode, StopController
    from core.orchestrator.session import Session

    session = Session(session_id="pause-stop")
    pause = PauseController()
    pause.pause(PauseMode.SAFE_WAIT)
    ctrl = StopController()
    state.register(session, ctrl)
    run = state.RunHandle(run_id="run_ps", session=session, controller=ctrl,
                          pause=pause, events=asyncio.Queue(), runner=None)
    state.runs[session.id] = run
    try:
        r = client.post("/api/task/pause-stop/stop")
        assert r.status_code == 200
        assert ctrl.token.is_cancelled
        assert pause.paused is False, "stop 必须解除暂停，否则循环卡死在闸门"
    finally:
        state.cleanup(session.id)


def test_pause_and_resume_endpoints(client):
    """暂停端点三档模式 + 恢复；无运行时 404。Pause modes and resume; 404 without a run."""
    import asyncio
    from core.api import state
    from core.orchestrator.control import PauseController, PauseMode
    from core.orchestrator.session import Session

    session = Session(session_id="pause-sess")
    pause = PauseController()
    run = state.RunHandle(
        run_id="run_pause", session=session, controller=__import__(
            "core.orchestrator.control", fromlist=["StopController"]).StopController(),
        pause=pause, events=asyncio.Queue(),
        runner=None,
    )
    state.runs[session.id] = run
    try:
        r = client.post("/api/task/pause-sess/pause", json={"mode": "stop"})
        assert r.status_code == 200
        assert r.json()["mode"] == "stop"
        assert pause.paused is True and pause.mode == PauseMode.SAFE_STOP

        assert client.post("/api/task/pause-sess/pause", json={"mode": "bogus"}).status_code == 400

        r2 = client.post("/api/task/pause-sess/pause/resume")
        assert r2.status_code == 200
        assert pause.paused is False
    finally:
        state.cleanup(session.id)

    assert client.post("/api/task/ghost/pause", json={"mode": "wait"}).status_code == 404
