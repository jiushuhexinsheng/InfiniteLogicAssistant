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
from core.logger import logger
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
from core.tasks.store import TaskStore

# 任务库存储（懒加载单例，便于测试替换）。
# Task-library store (lazy singleton, easy to swap in tests).
_task_store: TaskStore | None = None


def _get_task_store() -> TaskStore:
    """取任务库存储。Get the task-library store.

    Returns:
        任务库存储。The task store.
    """
    global _task_store
    if _task_store is None:
        _task_store = TaskStore()
    return _task_store


async def find_similar(goal: str) -> dict | None:
    """查找相似的历史成功任务（无命中返回 None）。

    Find a similar archived successful task, or None.

    Args:
        goal: 目标任务。The target goal.

    Returns:
        历史任务或 None。The archived task, or None.
    """
    return await _get_task_store().find_similar(goal)

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

# 完成确认的两个固定选项（任务模式用）。
# The two fixed options of the completion confirmation (used in task mode).
COMPLETION_OPTIONS = [
    {"value": "yes", "label": "完成了"},
    {"value": "no", "label": "没完成"},
]


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
        # 是否正阻塞在 ask()：供 /voice/utter 判断该会话是否已被占用。
        # Whether an ask() is currently pending, so /voice/utter can tell the session is busy.
        self.awaiting_answer = False

    async def notify(self, text: str) -> None:
        """向事件队列写入 notify 状态事件。Write a notify state event into the event queue."""
        await self.events.put(TaskStateEvent(state="notify", text=text, session_id=self.session_id).emit())

    async def ask(self, question: str, *, kind: str = "text", options: list | None = None) -> Answer:
        """写入 question 事件并阻塞等待操作者回答（串行化，同会话同时最多一个待答问题）。

        kind 与 options 随事件下发，前端据此决定渲染按钮还是输入框。

        Write a question event and block until the operator answers (serialized: at most
        one pending question per session). kind and options travel with the event so the
        frontend can decide between buttons and a text input.
        """
        # 串行化提问：同会话同时最多一个待答问题，避免并发子代理答非所问
        async with self._ask_lock:
            await self.events.put(
                QuestionEvent(question=question, session_id=self.session_id,
                              kind=kind, options=options or []).emit()
            )
            self.awaiting_answer = True
            try:
                return await self.answers.get()
            finally:
                self.awaiting_answer = False

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
                       messages: list[dict] | None = None, mode: str = "chat") -> None:
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
        # 先用历史成功任务预填：必须以 confirmed **重新** form_task，否则 missing 已由首次
        # form_task 算好、只填 task.params 不会让它变小（本功能的关键点）。
        # Prefill from a similar archived task first: form_task must be re-run with
        # `confirmed`, because `missing` has already been computed by the first call and
        # prefilling task.params alone would not shrink it — the crux of this feature.
        # 匹配用**用户原话**而非 task.goal：goal 是 LLM 归一化的产物，同一句话两次
        # 跑出的 goal 可能只相似 ~0.31（实测），使同一件事不可匹配。
        # Match on the user's ORIGINAL utterance, not task.goal: the goal is LLM-normalised
        # and the same sentence can yield goals only ~0.31 similar (measured), which makes
        # identical tasks unmatchable.
        hist = await find_similar(text)
        if hist is not None:
            await session.notify(f"参考了历史任务，已预填 {len(hist['params'])} 个参数")
            task = await form_task(intent, confirmed=hist["params"])
            session.task = task
            task.params = {**hist["params"], **task.params}
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
    # 任务模式：完成后询问「完成了吗」，答「完成了」才存档（需求：只记录成功的任务）。
    # Task mode: ask whether the task is done and archive only on "completed" — the
    # requirement is to record successful tasks only.
    if mode == "task" and result.get("status") == "done":
        answer = await session.ask("这个任务完成了吗？", kind="choice", options=COMPLETION_OPTIONS)
        if answer.choice == "yes":
            try:
                await _get_task_store().record(task, result, session_id=session.id, source_text=text)
            except Exception as e:
                logger.warning("任务存档失败: {}", e)  # 存档失败不该影响汇报

    session.set_state(SessionState.REPORTING)
    await events.put(TaskStateEvent(
        state="done", status=result["status"], summary=result["summary"], steps=result["steps"],
    ).emit())
    await events.put(DoneEvent().emit())
