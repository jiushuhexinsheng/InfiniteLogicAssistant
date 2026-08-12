# -*- coding: utf-8 -*-
"""编排管线 — 一次语音输入 → 意图 →（闲聊回复 | 任务：澄清→确认→执行→汇报）

事件写进 asyncio.Queue，由 server 的 SSE 生成器消费；
ask() 抛出 question 事件后阻塞，等待 /api/voice/answer 投递回答（人类在环）。
"""
import asyncio

from core.llm.stream import stream_chat
from core.orchestrator.clarify import run_clarify
from core.orchestrator.confirm import confirm_if_needed
from core.orchestrator.control import StopController
from core.orchestrator.executor import execute_task
from core.orchestrator.intent import judge_intent
from core.orchestrator.session import OperatorChannel, Session, SessionState
from core.orchestrator.task import Task, form_task


class EventQueueChannel(OperatorChannel):
    """notify/question 写事件队列；ask 等待操作者回答（/api/voice/answer 投递）。"""

    def __init__(self, events: asyncio.Queue, session_id: str):
        self.events = events
        self.session_id = session_id
        self.answers: asyncio.Queue = asyncio.Queue()

    async def notify(self, text: str) -> None:
        await self.events.put({"type": "task_state", "state": "notify", "text": text, "session_id": self.session_id})

    async def ask(self, question: str) -> str:
        await self.events.put({"type": "question", "question": question, "session_id": self.session_id})
        return await self.answers.get()

    def answer(self, text: str) -> None:
        self.answers.put_nowait(text)


async def _chit_chat_reply(text: str, events: asyncio.Queue) -> None:
    messages = [
        {"role": "system", "content": "你是小逻，用中文简洁友好地回复。"},
        {"role": "user", "content": text},
    ]
    async for evt in stream_chat(messages):
        if evt["type"] == "content_delta":
            await events.put({"type": "content_delta", "text": evt["text"]})


async def run_pipeline(text: str, session: Session, events: asyncio.Queue, controller: StopController) -> None:
    """完整编排，产出事件（以 done 事件收尾）。"""
    channel = EventQueueChannel(events, session.id)
    session.channel = channel
    session.append("user", text)
    session.set_state(SessionState.UNDERSTANDING)
    await events.put({"type": "task_state", "state": "understanding", "session_id": session.id})

    intent = await judge_intent(text)
    if intent.type == "chit_chat":
        session.set_state(SessionState.CHIT_CHAT)
        try:
            await _chit_chat_reply(text, events)
        except Exception as e:
            await events.put({"type": "error", "message": str(e)})
        await events.put({"type": "done"})
        return

    session.set_state(SessionState.FORMING_TASK)
    task: Task = await form_task(intent)
    session.task = task

    if task.missing:
        session.set_state(SessionState.CLARIFYING)
        task.params = await run_clarify(session, task)

    session.set_state(SessionState.CONFIRMING)
    ok = await confirm_if_needed(task, f"执行任务：{task.goal}", session)
    if not ok:
        await events.put({"type": "task_state", "state": "done", "status": "cancelled", "summary": "操作者未确认，任务取消"})
        await events.put({"type": "done"})
        return

    session.set_state(SessionState.EXECUTING)
    result = await execute_task(task, session, controller.token)
    session.set_state(SessionState.REPORTING)
    await events.put({
        "type": "task_state", "state": "done", "status": result["status"],
        "summary": result["summary"], "steps": result["steps"],
    })
    await events.put({"type": "done"})
