# -*- coding: utf-8 -*-
"""会话 TTL 清扫（docs/designs/10 5.1）。

背景：`session_ts` 只在注册时写，`sweep()` 会把仍在运行的 sessions/controllers/runs
一起 pop 掉，而且不取消 runner —— 长任务跨过 TTL 就人间蒸发。

Session TTL sweeping (docs/designs/10 5.1). `session_ts` was only written at
registration, so `sweep()` evicted sessions/controllers/runs that were still running
without cancelling the runner — a long task vanished once it crossed the TTL.
"""
import asyncio
import time

import pytest

from core.api import state
from core.orchestrator.control import StopController
from core.orchestrator.session import Session


def _old_ts() -> float:
    """一个肯定过期的注册时间戳。A registration timestamp that is definitely expired."""
    return time.time() - state.config.settings.server.session_ttl_s - 100


def _register(sid: str) -> Session:
    """注册一个会话（register 自带一次 sweep，先清干净外部状态）。"""
    state.sessions.clear()
    state.controllers.clear()
    state.session_ts.clear()
    state.session_created.clear()
    state.runs.clear()
    session = Session(session_id=sid)
    state.register(session, StopController())
    return session


@pytest.mark.asyncio
async def test_sweep_skips_live_run():
    """运行未完成的会话不被 TTL 清扫，runner 也不被取消。"""
    sid = "live-1"
    session = _register(sid)
    runner = asyncio.ensure_future(asyncio.sleep(60))
    run = state.RunHandle(run_id=f"run_{sid}", session=session,
                          controller=state.get_controller(sid), events=asyncio.Queue(),
                          runner=runner)
    state.set_run(sid, run)
    state.session_ts[sid] = _old_ts()

    state.sweep()

    assert state.get_session(sid) is session
    assert state.get_run(sid) is run
    assert not runner.cancelled()
    runner.cancel()
    await asyncio.gather(runner, return_exceptions=True)
    state.cleanup(sid)


@pytest.mark.asyncio
async def test_cleanup_cancels_unfinished_runner():
    """cleanup 移除条目前必须取消未完成的 runner（不再留下孤儿任务）。"""
    sid = "live-2"
    session = _register(sid)
    runner = asyncio.ensure_future(asyncio.sleep(60))
    run = state.RunHandle(run_id=f"run_{sid}", session=session,
                          controller=state.get_controller(sid), events=asyncio.Queue(),
                          runner=runner)
    state.set_run(sid, run)

    state.cleanup(sid)
    await asyncio.gather(runner, return_exceptions=True)

    assert runner.cancelled()
    assert state.get_session(sid) is None
    assert state.get_run(sid) is None


@pytest.mark.asyncio
async def test_sweep_evicts_finished_run():
    """已完成的运行仍按 TTL 回收。A finished run is still evicted by the TTL."""
    sid = "done-1"
    session = _register(sid)
    runner = asyncio.ensure_future(asyncio.sleep(0))
    await asyncio.gather(runner, return_exceptions=True)
    run = state.RunHandle(run_id=f"run_{sid}", session=session,
                          controller=state.get_controller(sid), events=asyncio.Queue(),
                          runner=runner)
    run.finished = True
    state.set_run(sid, run)
    state.session_ts[sid] = _old_ts()

    state.sweep()

    assert state.get_session(sid) is None
    assert state.get_run(sid) is None


def test_touch_refreshes_session_ttl():
    """事件产生时刷新活动时间戳，长会话不会因注册时间过旧被误清扫。"""
    sid = "touch-1"
    _register(sid)
    state.session_ts[sid] = _old_ts()

    state.touch(sid)

    assert state.session_ts[sid] > time.time() - 5
    state.cleanup(sid)
