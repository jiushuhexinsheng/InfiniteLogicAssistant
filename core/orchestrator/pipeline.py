# -*- coding: utf-8 -*-
"""编排管线 — 一次语音输入 → 意图 →（闲聊回复 | 任务：澄清→确认→执行→汇报）

事件写进 asyncio.Queue，由 server 的 SSE 生成器消费；
ask() 抛出 question 事件后阻塞，等待 /api/voice/answer 投递回答（人类在环）。

Orchestration pipeline — one voice input → intent → (chit-chat reply | task:
clarify → confirm → execute → report). Events are written into an asyncio.Queue
consumed by the server's SSE generator; ask() blocks after emitting a question
event until /api/voice/answer delivers the answer (human in the loop).
"""
import asyncio

from core.llm.client import get_llm_client
from core.memory.context import get_facts_store
from core.memory.extract import extract_and_store
from core.orchestrator.clarify import run_clarify
from core.orchestrator.confirm import confirm_if_needed
from core.orchestrator.control import StopController
from core.orchestrator.events import (
    ContentDeltaEvent, DoneEvent, ErrorEvent, QuestionEvent, TaskStateEvent,
)
from core.orchestrator.executor import execute_task
from core.orchestrator.intent import judge_intent
from core.orchestrator.session import Answer, OperatorChannel, Session, SessionState
from core.orchestrator.task import Task, form_task
from core.prompts import CHIT_CHAT_SYSTEM

# 后台任务引用集：CPython 的事件循环对 Task 仅持弱引用，不保留句柄的任务
# 可能在执行完成前被垃圾回收 —— 而 extract_and_store 内部吞掉所有异常
# （core/memory/extract.py），后果是长期记忆提取静默不发生、无任何报错痕迹。
#
# Background-task reference set: CPython's event loop only holds weak references
# to Tasks, so a task without a retained handle may be garbage-collected before it
# finishes — and extract_and_store swallows all exceptions internally
# (core/memory/extract.py), making the consequence a silent loss of long-term
# fact extraction with no error trace.
_bg_tasks: set[asyncio.Task] = set()


def _spawn_bg(coro) -> asyncio.Task:
    """启动后台任务并持有引用，完成后自动丢弃。

    Start a background task while holding a reference, discarding it on completion.

    Args:
        coro: 要调度的协程。The coroutine to schedule.

    Returns:
        已调度的 Task。The scheduled Task.
    """
    t = asyncio.ensure_future(coro)
    _bg_tasks.add(t)
    t.add_done_callback(_bg_tasks.discard)
    return t


class EventQueueChannel(OperatorChannel):
    """notify/question 写事件队列；ask 等待操作者回答（/api/voice/answer 投递）。

    Writes notify/question into the event queue; ask waits for the operator's
    answer (delivered via /api/voice/answer).
    """

    def __init__(self, events: asyncio.Queue, session_id: str):
        """初始化通道：绑定事件队列与会话 ID，并创建回答队列与提问锁。

        Initialize the channel with the event queue and session id, creating an
        answer queue and an ask lock.
        """
        self.events = events
        self.session_id = session_id
        self.answers: asyncio.Queue = asyncio.Queue()
        self._ask_lock = asyncio.Lock()

    async def notify(self, text: str) -> None:
        """向事件队列写入 notify 状态事件。Write a notify state event into the event queue."""
        await self.events.put(TaskStateEvent(state="notify", text=text, session_id=self.session_id).emit())

    async def ask(self, question: str, *, kind: str = "clarify") -> Answer:
        """写入 question 事件并阻塞等待操作者回答（串行化，同会话同时最多一个待答问题）。

        kind 随事件下发：前端据 kind="confirm" 渲染确认按钮而非文本输入。

        Write a question event and block until the operator answers (serialized:
        at most one pending question per session). kind travels with the event so
        the frontend renders confirm buttons instead of a text input for
        kind="confirm".
        """
        # 串行化提问：同会话同时最多一个待答问题，避免并发子代理答非所问
        async with self._ask_lock:
            await self.events.put(
                QuestionEvent(question=question, session_id=self.session_id, kind=kind).emit()
            )
            return await self.answers.get()

    def answer(self, text: str, choice: str | None = None) -> None:
        """投递操作者回答到回答队列（由 /api/voice/answer 调用）。

        choice 为结构化选择（"yes" / "no"），由前端确认按钮回传。

        Deliver the operator's answer into the answer queue (called by
        /api/voice/answer). choice is the structured selection ("yes" / "no")
        returned by the frontend's confirmation buttons.
        """
        self.answers.put_nowait(Answer(text=text, choice=choice))


async def _chit_chat_reply(session: Session, events: asyncio.Queue, text: str) -> None:
    """生成闲聊回复：流式发射 content_delta 事件并把完整回复记入会话历史。

    Generate a chit-chat reply: stream content_delta events and record the full
    reply into the session history.
    """
    messages = [{"role": "system", "content": CHIT_CHAT_SYSTEM}]
    messages.extend(session.summary(8))  # 含当前用户消息 → 多轮闲聊
    reply_parts: list[str] = []
    # 走 LLM client：与任务执行共享重试/熔断/模型 failover
    async for evt in get_llm_client().retry_stream_chat(messages):
        if evt["type"] == "content_delta":
            await events.put(ContentDeltaEvent(text=evt["text"]).emit())
            reply_parts.append(evt["text"])
    if reply_parts:
        session.append("assistant", "".join(reply_parts))  # 记录完整回复到会话历史


async def run_pipeline(text: str, session: Session, events: asyncio.Queue,
                       controller: StopController, channel: OperatorChannel | None = None,
                       messages: list[dict] | None = None) -> None:
    """完整编排，产出事件（以 done 事件收尾）。channel 缺省用 SSE 队列通道。

    messages 为前端多轮历史种子（含当前用户消息）；缺省时把 text 记为当前用户消息。

    Full orchestration that emits events (ending with a done event). The channel
    defaults to the SSE queue channel. messages is the frontend multi-turn history
    seed (including the current user message); when absent, text is recorded as
    the current user message.
    """
    if channel is None:
        channel = EventQueueChannel(events, session.id)
    session.channel = channel
    if messages:
        session.messages = [
            m for m in messages
            if isinstance(m, dict) and m.get("role") in ("user", "assistant")
            and isinstance(m.get("content"), str)
        ]
        # 确保当前用户消息在末尾（调用方可能只传历史）
        if not session.messages or session.messages[-1].get("role") != "user" or session.messages[-1].get("content") != text:
            session.messages.append({"role": "user", "content": text})
    else:
        session.append("user", text)
    session.set_state(SessionState.UNDERSTANDING)
    await events.put(TaskStateEvent(state="understanding", session_id=session.id).emit())

    intent = await judge_intent(text)
    if intent.type == "chit_chat":
        session.set_state(SessionState.CHIT_CHAT)
        try:
            await _chit_chat_reply(session, events, text)
        except Exception as e:
            await events.put(ErrorEvent(message=str(e)).emit())
        await events.put(DoneEvent().emit())
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
        await events.put(TaskStateEvent(state="done", status="cancelled", summary="操作者未确认，任务取消").emit())
        await events.put(DoneEvent().emit())
        return

    session.set_state(SessionState.EXECUTING)
    result = await execute_task(task, session, controller.token, events)
    # 任务后异步提取事实写长期记忆（不阻塞回复，失败静默）
    if result.get("status") in ("done", "failed"):
        _spawn_bg(extract_and_store(task, result, get_facts_store()))
    session.set_state(SessionState.REPORTING)
    await events.put(TaskStateEvent(
        state="done", status=result["status"], summary=result["summary"], steps=result["steps"],
    ).emit())
    await events.put(DoneEvent().emit())
