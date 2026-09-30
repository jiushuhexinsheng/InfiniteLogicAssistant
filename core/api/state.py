# -*- coding: utf-8 -*-
"""编排会话运行时状态 — 会话/停止控制器注册表 + 运行句柄（seq/ring buffer）+ TTL 清理 + 任务落盘

Orchestration session runtime state — session/stop-controller registry + run
handles (seq / ring buffer for SSE resume) + TTL sweeping + task persistence to disk
"""
import json
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from core import config as config
from core.logger import logger
from core.orchestrator.control import StopController
from core.orchestrator.session import Session

# 编排会话与停止控制器注册表（key = session_id）
sessions: dict[str, Session] = {}
controllers: dict[str, StopController] = {}
session_ts: dict[str, float] = {}
SESSION_TTL = 30 * 60  # 会话空闲 30 分钟回收


@dataclass
class RunHandle:
    """一次编排运行的句柄（docs/designs/06）：事件队列、runner、seq 与 ring buffer。

    断线恢复的全部状态都在这里：`buffer` 存已被首条连接消费掉的事件（带定型 seq），
    `events` 队列持有断线期间流入的事件（重连后由新连接续消费、续编号）——
    两段拼起来即完整缺口回放。

    Handle for one orchestration run (docs/designs/06): event queue, runner, seq and
    ring buffer. All state needed for resume lives here: `buffer` holds events the
    first connection already consumed (with a fixed seq), `events` holds what flowed
    in while disconnected (the reconnecting consumer continues numbering them) —
    the two segments concatenate into a complete gap replay.
    """

    run_id: str
    session: Session
    controller: StopController
    events: "Any"  # asyncio.Queue（延迟导入避免环）。asyncio.Queue (deferred to avoid a cycle).
    runner: "Any"  # asyncio.Task。asyncio.Task.
    buffer: deque = field(default_factory=lambda: deque(maxlen=500))
    next_seq: int = 1
    connected: bool = True
    finished: bool = False          # done 已发出 / runner 收尾。done emitted / runner wrapped up.
    closed: bool = False            # 收尾已执行（幂等护栏）。Wrap-up already ran (idempotence guard).
    grace_task: "Any | None" = None  # 断线宽限看门狗。Disconnect grace watchdog.


# 运行句柄注册表（key = session_id）。Run-handle registry (key = session_id).
runs: dict[str, RunHandle] = {}


def get_run(session_id: str) -> RunHandle | None:
    """按 id 取运行句柄；不存在返回 None。Get a run handle by id, or None.

    Args:
        session_id: 会话 id。The session id.

    Returns:
        运行句柄或 None。The run handle or None.
    """
    return runs.get(session_id)


def set_run(session_id: str, run: RunHandle) -> RunHandle | None:
    """登记运行句柄；同 id 已有在跑的旧运行时先打掉（新回合取代旧回合）。

    返回被取代的旧句柄（调用方负责收尾），无旧运行返回 None。

    Register a run handle; when an older run for the same id is still live it is
    dropped first (a new turn supersedes the old). Returns the superseded handle
    (the caller wraps it up), or None when there was no older run.
    """
    old = runs.get(session_id)
    runs[session_id] = run
    return old if old is not None and old is not run and not old.finished else None


def drop_run(session_id: str) -> RunHandle | None:
    """从注册表摘下运行句柄（不取消 runner —— 收尾由调用方决定）。

    Remove a run handle from the registry (does not cancel the runner — the caller
    decides how to wrap it up).
    """
    return runs.pop(session_id, None)


def register(session: Session, controller: StopController) -> None:
    """注册会话及其停止控制器，记录时间戳并顺带清理超时会话。

    Register a session and its stop controller, record the timestamp and sweep
    expired sessions as a side effect.

    Args:
        session: 编排会话。The orchestration session.
        controller: 该会话的停止控制器。The session's stop controller.
    """
    sessions[session.id] = session
    controllers[session.id] = controller
    session_ts[session.id] = time.time()
    sweep()


def get_session(session_id: str) -> Session | None:
    """按 id 取会话；不存在时返回 None。

    Get a session by id, or None if it does not exist.

    Args:
        session_id: 会话 id。The session id.

    Returns:
        会话对象或 None。The session object, or None.
    """
    return sessions.get(session_id)


def get_controller(session_id: str) -> StopController | None:
    """按 id 取停止控制器；不存在时返回 None。

    Get the stop controller by id, or None if it does not exist.

    Args:
        session_id: 会话 id。The session id.

    Returns:
        停止控制器或 None。The stop controller, or None.
    """
    return controllers.get(session_id)


def sweep() -> None:
    """回收超时会话（防止长时间运行内存泄漏）。

    Reclaim expired sessions (prevent memory leaks on long-running processes).
    """
    now = time.time()
    for sid in [sid for sid, ts in session_ts.items() if now - ts > SESSION_TTL]:
        cleanup(sid)


def cleanup(session_id: str) -> None:
    """流结束时移除注册表条目。

    Remove registry entries when a stream ends.
    """
    sessions.pop(session_id, None)
    controllers.pop(session_id, None)
    session_ts.pop(session_id, None)
    runs.pop(session_id, None)


def _conv_summary(messages: list[dict], task: dict | None) -> str:
    """历史列表摘要：优先任务目标，其次最近一条助手回复。

    Conversation summary: prefer the task goal, else the most recent assistant reply.
    """
    if task and task.get("goal"):
        return str(task["goal"])[:80]
    for m in reversed(messages):
        if m.get("role") == "assistant" and m.get("content"):
            return str(m["content"])[:80]
    return ""


async def persist(session: Session, created: float | None = None) -> None:
    """把完成的会话/任务落盘到 data/tasks/<id>.json，并保存完整会话历史。best-effort。

    Persist the finished session/task to data/tasks/<id>.json and save the full
    conversation history. Best-effort.
    """
    try:
        tasks_dir = config.ROOT_DIR / "data" / "tasks"
        tasks_dir.mkdir(parents=True, exist_ok=True)
        state_str: str = session.state.value if hasattr(session.state, "value") else str(session.state)
        task_dict: dict | None = asdict(session.task) if session.task is not None else None
        record = {
            "session_id": session.id,
            "created": datetime.fromtimestamp(created).isoformat() if created else None,
            "finished": datetime.now().isoformat(),
            "state": state_str,
            "messages": [
                {"role": m.get("role"), "content": m.get("content"),
                 "blocks": m.get("blocks"), "turn_id": m.get("turn_id"), "ts": m.get("ts")}
                for m in session.messages[-20:] if isinstance(m, dict)
            ],
            "task": task_dict,
        }
        (tasks_dir / f"{session.id}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        # 完整会话历史（控制台「历史」tab 数据源）
        try:
            from core.session.history import get_history_store
            await get_history_store().save_conversation(
                session.id, session.messages,
                status=state_str,
                summary=_conv_summary(session.messages, task_dict),
            )
        except Exception as e2:
            logger.warning("历史保存失败 {}: {}", session.id, e2)
    except Exception as e:
        logger.warning("会话落盘失败 {}: {}", session.id, e)
