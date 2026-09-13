# -*- coding: utf-8 -*-
"""定时任务执行 — 无人值守：需要澄清/确认的任务自动跳过，只读任务直接执行
Scheduled task execution — unattended: tasks requiring clarification/confirmation are skipped automatically, while read-only tasks run directly.

结果落盘到会话历史（data/tasks/ + history.db，控制台「历史」可见）；
存在被跳过的高风险操作时记录 warning 提醒操作者。
Results are persisted to the session history (data/tasks/ + history.db, visible in the console "History"); a warning is logged to alert the operator when high-risk operations were skipped.
"""
import asyncio
import time

from core.api import state
from core.logger import logger
from core.orchestrator.control import StopController
from core.orchestrator.pipeline import run_pipeline
from core.orchestrator.session import Answer, Session


class _SilentChannel:
    """无人值守通道：提问返回空 → 澄清停止、确认拒绝；通知记日志。
    Unattended channel: questions return an empty string, so clarification stops and confirmation is rejected; notifications are logged.

    rejected 记录被忽略的确认/澄清问题（操作者不在场无法应答），供调用方提醒。
    rejected records the confirmation/clarification questions that were ignored (unanswerable while the operator is away) so the caller can alert about them.
    """

    def __init__(self) -> None:
        """初始化被拒绝问题列表。Initializes the list of rejected questions."""
        self.rejected: list[str] = []

    async def ask(self, question: str, *, kind: str = "text", options: list | None = None) -> Answer:
        """向操作者提问：无人值守时记录问题并返回空回答（无 choice → 确认被拒）。
        Asks the operator a question: when unattended, records the question and returns an empty answer (no choice → confirmation rejected)."""
        self.rejected.append(question)
        return Answer()

    async def notify(self, text: str) -> None:
        """通知操作者：无人值守时仅记日志。
        Notifies the operator: when unattended, only logs the notification."""
        logger.info("定时任务通知: {}", text)


async def _drain_result(events: asyncio.Queue) -> tuple[str, str]:
    """排空事件队列，提取最终 (status, summary)。
    Drains the event queue and extracts the final (status, summary).

    run_pipeline 是同步 await 完成的，返回前 done 事件必然已入队，
    因此只需排空队列既有事件即可（上游未放 done 时安全返回空）。
    run_pipeline completes via a plain await, so the done event is guaranteed to be queued before it returns; it is therefore enough to drain the events already in the queue (safely returning empty when the upstream has not posted done).
    """
    status = ""
    summary = ""
    while True:
        try:
            evt = events.get_nowait()
        except asyncio.QueueEmpty:
            break
        if evt.get("type") == "task_state" and evt.get("state") == "done":
            status = evt.get("status", "")
            summary = evt.get("summary", "")
    return status, summary


async def run_scheduled(prompt: str) -> dict:
    """执行一个定时任务 prompt（阻塞到完成；需澄清/确认的自动取消）。
    Runs a scheduled task prompt (blocks until completion; tasks requiring clarification/confirmation are auto-cancelled).

    结束后把会话落盘（控制台「历史」可见被拒/失败原因）；
    存在被跳过的高风险操作时记录 warning 提醒。返回 {status, summary, rejected}。
    Afterwards the session is persisted (the console "History" shows the rejected/failure reasons); a warning is logged when high-risk operations were skipped. Returns {status, summary, rejected}.
    """
    session = Session()
    controller = StopController()
    channel = _SilentChannel()
    events: asyncio.Queue = asyncio.Queue()
    try:
        await run_pipeline(prompt, session, events, controller, channel=channel)
        status, summary = await _drain_result(events)
        await state.persist(session, time.time())
        if channel.rejected:
            joined = "；".join(channel.rejected)
            logger.warning("定时任务存在无人应答的高风险操作，已跳过: {}（{}）", prompt, joined)
        return {"status": status, "summary": summary, "rejected": channel.rejected}
    except Exception as e:
        logger.warning("定时任务执行失败: {} → {}", prompt, e)
        return {"status": "error", "summary": str(e), "rejected": channel.rejected}
