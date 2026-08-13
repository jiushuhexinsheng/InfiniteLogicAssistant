# -*- coding: utf-8 -*-
"""编排管线 — 一次语音输入 → 意图 →（闲聊回复 | 任务：澄清→确认→执行→汇报）

事件写进 asyncio.Queue，由 server 的 SSE 生成器消费；
ask() 抛出 question 事件后阻塞，等待 /api/voice/answer 投递回答（人类在环）。
"""
import asyncio

from core.llm.stream import stream_chat
from core.memory.context import get_facts_store
from core.memory.extract import extract_and_store
from core.orchestrator.clarify import run_clarify
from core.orchestrator.confirm import confirm_if_needed
from core.orchestrator.control import StopController
from core.orchestrator.executor import execute_task
from core.orchestrator.intent import judge_intent
from core.orchestrator.session import OperatorChannel, Session, SessionState
from core.orchestrator.task import Task, form_task
from core.recent import append_turn
from core.status import set_status


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


async def _chit_chat_reply(text: str, events: asyncio.Queue) -> str:
    messages = [
        {"role": "system", "content": "你是小逻，用中文简洁友好地回复。"},
        {"role": "user", "content": text},
    ]
    acc = ""
    async for evt in stream_chat(messages):
        if evt["type"] == "content_delta":
            acc += evt["text"]
            await events.put({"type": "content_delta", "text": evt["text"]})
    return acc


async def run_pipeline(text: str, session: Session, events: asyncio.Queue,
                       controller: StopController, channel: OperatorChannel | None = None) -> None:
    """完整编排，产出事件（以 done 事件收尾）。channel 缺省用 SSE 队列通道。"""
    if channel is None:
        channel = EventQueueChannel(events, session.id)
    session.channel = channel
    session.append("user", text)
    session.set_state(SessionState.UNDERSTANDING)
    await events.put({"type": "task_state", "state": "understanding", "session_id": session.id})
    set_status(state="understanding", activity=text)

    intent = await judge_intent(text)
    if intent.type == "chit_chat":
        session.set_state(SessionState.CHIT_CHAT)
        set_status(state="chit_chat", activity=intent.summary)
        try:
            reply = await _chit_chat_reply(text, events)
            set_status(state="done", summary=reply)
            append_turn(user=text, assistant=reply, source="chit")
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
    set_status(state="executing", activity=task.goal)
    result = await execute_task(task, session, controller.token)
    # 任务后异步提取事实写长期记忆（不阻塞回复，失败静默）
    if result.get("status") in ("done", "failed"):
        asyncio.ensure_future(extract_and_store(task, result, get_facts_store()))
    set_status(state="done", summary=result.get("summary", ""))
    append_turn(user=text, assistant=result.get("summary", ""),
                tools=[s.get("tool", "") for s in result.get("steps", [])])
    session.set_state(SessionState.REPORTING)
    await events.put({
        "type": "task_state", "state": "done", "status": result["status"],
        "summary": result["summary"], "steps": result["steps"],
    })
    await events.put({"type": "done"})
