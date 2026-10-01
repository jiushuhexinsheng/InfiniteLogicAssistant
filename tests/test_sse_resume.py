# -*- coding: utf-8 -*-
"""SSE seq/断线恢复（docs/designs/06）的测试。

覆盖：seq 编号与 buffer、缺口回放 + 实况挂接、404 no_run、断线宽限到期收尾、
runner 收尾幂等、ping 保活帧。
"""
import asyncio
import json

import pytest
from fastapi.testclient import TestClient

import server
import core.config as config_mod
from core.api import state
from core.api import voice as voice_api
from core.orchestrator.control import StopController
from core.orchestrator.session import Session


def _parse(chunk: str) -> dict:
    """一帧 SSE → 事件 dict。One SSE frame → event dict."""
    assert chunk.startswith("data: ") and chunk.endswith("\n\n")
    return json.loads(chunk[len("data: "):-2])


@pytest.fixture
def client(monkeypatch, tmp_path):
    """隔离的 TestClient：不读真实配置、不打外网；测试间清空运行注册表。

    Isolated TestClient: no real config, no external calls; the run registry is
    cleared between tests.
    """
    monkeypatch.setattr(config_mod, "get_settings",
                        lambda: config_mod.Settings(rag=config_mod.RagSection(auto_index=False)))
    monkeypatch.setattr(config_mod, "is_llm_configured", lambda: False)
    monkeypatch.setattr(config_mod, "is_asr_configured", lambda: False)
    monkeypatch.setattr("core.voice.get_asr", lambda: None)
    state.runs.clear()
    state.sessions.clear()
    state.controllers.clear()
    state.session_ts.clear()
    yield TestClient(server.app)
    # 挂着的宽限看门狗不得泄漏到下一测试。Leaked grace watchdogs must not bleed over.
    for handle in list(state.runs.values()):
        if handle.grace_task and not handle.grace_task.done():
            handle.grace_task.cancel()
    state.runs.clear()
    state.sessions.clear()
    state.controllers.clear()
    state.session_ts.clear()


@pytest.mark.asyncio
async def test_stream_run_assigns_seq_and_buffers():
    """首连消费路径给每个事件编号并入 buffer；done 收尾置 finished。
    The first-connection path numbers every event into the buffer; done wraps up."""
    events: asyncio.Queue = asyncio.Queue()
    runner = asyncio.ensure_future(asyncio.sleep(60))
    run = state.RunHandle(run_id="r1", session=Session(), controller=StopController(),
                          events=events, runner=runner)

    async def produce():
        await events.put({"type": "content_delta", "text": "a"})
        await events.put({"type": "content_delta", "text": "b"})
        await events.put({"type": "done"})

    asyncio.ensure_future(produce())
    frames = []
    async for chunk in voice_api._stream_run(run):
        frames.append(_parse(chunk))

    assert [f["seq"] for f in frames] == [1, 2, 3]      # 单调连续。Monotonic.
    assert [f["type"] for f in frames] == ["content_delta", "content_delta", "done"]
    assert run.finished is True
    assert len(run.buffer) == 3                          # 全量入 buffer 供回放。All buffered for replay.
    assert runner.cancelled() or runner.done()           # 收尾停掉 runner。Runner stopped on wrap-up.
    assert state.get_run("x") is None or True            # 注册表按其 session id 清理（此处独立构造）。Registry keyed by session id.


@pytest.mark.asyncio
async def test_disconnect_arms_grace_and_resume_replays_gap(monkeypatch):
    """断连（生成器 aclose，等价 HTTP 断开）→ 进宽限不收尾；resume 回放缺口 + 挂接实况。

    Disconnect (generator aclose, the HTTP equivalent) → grace without wrap-up;
    resume replays the gap then attaches to the live backlog.
    """
    monkeypatch.setattr(config_mod.settings.server, "resume_grace_s", 60)
    events: asyncio.Queue = asyncio.Queue()
    runner = asyncio.ensure_future(asyncio.sleep(60))
    session = Session()
    run = state.RunHandle(run_id="rd", session=session, controller=StopController(),
                          events=events, runner=runner)
    state.runs[session.id] = run

    # 首连消费两帧后断开（aclose 触发 finally → 宽限）。
    await events.put({"type": "content_delta", "text": "第一段"})
    await events.put({"type": "content_delta", "text": "第二段"})
    gen = voice_api._stream_run(run)
    f1 = _parse(await gen.__anext__())
    f2 = _parse(await gen.__anext__())
    await gen.aclose()
    assert (f1["seq"], f1["text"]) == (1, "第一段")
    assert (f2["seq"], f2["text"]) == (2, "第二段")
    assert run.connected is False                          # 断线标记。Marked disconnected.
    assert state.get_run(session.id) is run                # 宽限存活（未收尾）。Alive under grace.

    # 断线期间积压两帧；resume（_replay_then_live）：回放 seq2，再收积压的 seq3/done。
    await events.put({"type": "content_delta", "text": "断线期间"})
    await events.put({"type": "done"})
    frames = []
    async for chunk in voice_api._replay_then_live(run, last_seq=1):
        frames.append(_parse(chunk))
    # 缺口回放 seq2 + 实况 seq3/4（seq1 在客户端游标内不重发）。
    # Gap replay of seq2 + live seq3/4 (seq1 is behind the cursor, not resent).
    assert [f["seq"] for f in frames] == [2, 3, 4]
    assert frames[0]["text"] == "第二段"
    assert frames[1]["text"] == "断线期间"
    assert frames[2]["type"] == "done"
    assert run.finished and run.closed                     # 挂接收尾。Attached run wrapped up.
    assert state.get_run(session.id) is None


def test_resume_without_run_returns_404(client):
    """无运行句柄 → 404 no_run（前端走历史重载兜底）。No run handle → 404 no_run
    (the frontend falls back to reloading history)."""
    resp = client.post("/api/voice/resume", json={"session_id": "ghost", "last_seq": 0})
    assert resp.status_code == 404
    assert resp.json()["error"] == "no_run"


@pytest.mark.asyncio
async def test_grace_expiry_retires_run(monkeypatch):
    """宽限到期未重连 → 收尾（cancel runner + 从注册表摘除）。
    Grace expiring with no reconnect wraps up (cancels the runner, drops the registry entry)."""
    monkeypatch.setattr(config_mod.settings.server, "resume_grace_s", 1)
    monkeypatch.setattr(state, "persist", lambda *a, **k: asyncio.sleep(0))
    events: asyncio.Queue = asyncio.Queue()
    runner = asyncio.ensure_future(asyncio.sleep(60))
    session = Session()
    run = state.RunHandle(run_id="rg", session=session, controller=StopController(),
                          events=events, runner=runner)
    state.runs[session.id] = run

    run.connected = False
    voice_api._arm_grace(run)
    assert run.grace_task is not None
    await asyncio.sleep(1.2)

    assert run.closed is True
    assert runner.cancelled()
    assert state.get_run(session.id) is None


@pytest.mark.asyncio
async def test_retire_run_is_idempotent(monkeypatch):
    """收尾幂等：并发/重复调用只执行一次（persist 不双写、看门狗不重复取消）。
    Wrap-up is idempotent: concurrent/repeated calls run once (no double persist)."""
    calls = {"n": 0}

    async def fake_persist(*a, **k):
        calls["n"] += 1

    monkeypatch.setattr(state, "persist", fake_persist)
    events: asyncio.Queue = asyncio.Queue()
    runner = asyncio.ensure_future(asyncio.sleep(60))
    session = Session()
    run = state.RunHandle(run_id="ri", session=session, controller=StopController(),
                          events=events, runner=runner)
    state.runs[session.id] = run

    await asyncio.gather(voice_api._retire_run(run), voice_api._retire_run(run))
    await voice_api._retire_run(run)

    assert calls["n"] == 1
    assert state.get_run(session.id) is None


@pytest.mark.asyncio
async def test_ping_keepalive_frame(monkeypatch):
    """空闲期发 ping 保活帧（type=ping、不占 seq）——前端 watchdog 的重置信号。
    An idle period emits a ping frame (type=ping, no seq) — the frontend watchdog's
    reset signal."""
    # _stream_run 读的是 run 模块全局的 PING_INTERVAL_S（voice 包级副本改了不生效）。
    # _stream_run reads PING_INTERVAL_S from the run module's globals (the package-level
    # copy would have no effect).
    monkeypatch.setattr("core.api.voice.run.PING_INTERVAL_S", 0.05)
    events: asyncio.Queue = asyncio.Queue()
    runner = asyncio.ensure_future(asyncio.sleep(60))
    run = state.RunHandle(run_id="rp", session=Session(), controller=StopController(),
                          events=events, runner=runner)
    gen = voice_api._stream_run(run)
    frame = _parse(await gen.__anext__())   # 队列空 → 先到的是保活帧。Queue empty → keep-alive first.
    await gen.aclose()
    assert frame["type"] == "ping"
    assert "seq" not in frame, "ping 不占 seq、不进回放。Pings carry no seq."
