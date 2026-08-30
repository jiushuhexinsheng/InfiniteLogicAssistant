# -*- coding: utf-8 -*-
"""定时任务执行 — 无人值守：需要澄清/确认的任务自动跳过，只读任务直接执行

结果落盘到会话历史（data/tasks/ + history.db，控制台「历史」可见）；
存在被跳过的高风险操作时记录 warning 提醒操作者。
"""
import asyncio
import time

from core.api import state
from core.logger import logger
from core.orchestrator.control import StopController
from core.orchestrator.pipeline import run_pipeline
from core.orchestrator.session import Session


class _SilentChannel:
    """无人值守通道：提问返回空 → 澄清停止、确认拒绝；通知记日志。

    rejected 记录被忽略的确认/澄清问题（操作者不在场无法应答），供调用方提醒。
    """

    def __init__(self) -> None:
        self.rejected: list[str] = []

    async def ask(self, question: str) -> str:
        self.rejected.append(question)
        return ""

    async def notify(self, text: str) -> None:
        logger.info("定时任务通知: {}", text)


async def _drain_result(events: asyncio.Queue) -> tuple[str, str]:
    """排空事件队列，提取最终 (status, summary)。

    run_pipeline 是同步 await 完成的，返回前 done 事件必然已入队，
    因此只需排空队列既有事件即可（上游未放 done 时安全返回空）。
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

    结束后把会话落盘（控制台「历史」可见被拒/失败原因）；
    存在被跳过的高风险操作时记录 warning 提醒。返回 {status, summary, rejected}。
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
