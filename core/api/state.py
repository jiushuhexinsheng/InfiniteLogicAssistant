# -*- coding: utf-8 -*-
"""编排会话运行时状态 — 会话/停止控制器注册表 + TTL 清理 + 任务落盘"""
import json
import time
from dataclasses import asdict
from datetime import datetime

from core import config as config
from core.logger import logger
from core.orchestrator.control import StopController
from core.orchestrator.session import Session

# 编排会话与停止控制器注册表（key = session_id）
sessions: dict[str, Session] = {}
controllers: dict[str, StopController] = {}
session_ts: dict[str, float] = {}
SESSION_TTL = 30 * 60  # 会话空闲 30 分钟回收


def register(session: Session, controller: StopController) -> None:
    sessions[session.id] = session
    controllers[session.id] = controller
    session_ts[session.id] = time.time()
    sweep()


def get_session(session_id: str) -> Session | None:
    return sessions.get(session_id)


def get_controller(session_id: str) -> StopController | None:
    return controllers.get(session_id)


def sweep() -> None:
    """回收超时会话（防止长时间运行内存泄漏）。"""
    now = time.time()
    for sid in [sid for sid, ts in session_ts.items() if now - ts > SESSION_TTL]:
        cleanup(sid)


def cleanup(session_id: str) -> None:
    """流结束时移除注册表条目。"""
    sessions.pop(session_id, None)
    controllers.pop(session_id, None)
    session_ts.pop(session_id, None)


def _conv_summary(messages: list[dict], task: dict | None) -> str:
    """历史列表摘要：优先任务目标，其次最近一条助手回复。"""
    if task and task.get("goal"):
        return str(task["goal"])[:80]
    for m in reversed(messages):
        if m.get("role") == "assistant" and m.get("content"):
            return str(m["content"])[:80]
    return ""


async def persist(session: Session, created: float | None = None) -> None:
    """把完成的会话/任务落盘到 data/tasks/<id>.json，并保存完整会话历史。best-effort。"""
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
                {"role": m.get("role"), "content": m.get("content")}
                for m in session.messages[-20:] if isinstance(m, dict)
            ],
            "task": task_dict,
        }
        (tasks_dir / f"{session.id}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        # 完整会话历史（控制台「历史」tab 数据源）
        try:
            from core.history import get_history_store
            await get_history_store().save_conversation(
                session.id, session.messages,
                status=state_str,
                summary=_conv_summary(session.messages, task_dict),
            )
        except Exception as e2:
            logger.warning("历史保存失败 {}: {}", session.id, e2)
    except Exception as e:
        logger.warning("会话落盘失败 {}: {}", session.id, e)
