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
from uuid import uuid4

from core import config
from core.llm.client import get_llm_client
from core.logger import logger
from core.memory.context import get_facts_store
from core.memory.extract import extract_and_store
from core.orchestrator.clarify import run_clarify
from core.orchestrator.confirm import confirm_if_needed
from core.orchestrator.control import StopController
from core.orchestrator.events import (
    AnswerEvent, ContentDeltaEvent, DoneEvent, ErrorEvent, QuestionEvent,
    TaskStateEvent, from_llm_event,
)
from core.orchestrator.executor import execute_task
from core.orchestrator.intent import judge_intent
from core.orchestrator.session import ABANDON_REASON, Answer, OperatorChannel, Session, SessionState
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
# 可能在执行完成前被垃圾回收。done 回调里顺带观察异常（task.exception()）——
# 未被协程内部接住的异常若无人观察，只会进 loop 的 exception handler，排障无从下手。
#
# Background-task reference set: CPython's event loop only holds weak references to
# Tasks, so a task without a retained handle may be garbage-collected before it
# finishes. The done callback also observes exceptions (task.exception()) — an
# exception that escapes the coroutine with no observer only reaches the loop's
# exception handler, leaving nothing to debug from.
_bg_tasks: set[asyncio.Task] = set()


def _on_bg_done(t: asyncio.Task) -> None:
    """后台任务收尾：丢弃引用 + 观察未接住的异常（留 warning 痕迹）。

    Background-task wrap-up: drop the reference and observe any exception that
    escaped the coroutine (leaving a warning trace).
    """
    _bg_tasks.discard(t)
    if t.cancelled():
        return
    exc = t.exception()
    if exc is not None:
        logger.warning("后台任务未捕获异常: {}", exc)

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
    t.add_done_callback(_on_bg_done)
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
        # 当前待答问题的 qid（ask 时生成、答后清空）：/api/voice/answer 携带 qid 时校验，
        # 防陈旧语音作答错配到新问题。
        # qid of the pending question (generated in ask, cleared once answered):
        # /api/voice/answer validates it when present, so a stale voice answer
        # cannot be mismatched onto a newer question.
        self.pending_qid: str | None = None

    async def notify(self, text: str) -> None:
        """向事件队列写入 notify 状态事件。Write a notify state event into the event queue."""
        await self.events.put(TaskStateEvent(state="notify", text=text, session_id=self.session_id).emit())

    async def ask(self, question: str, *, kind: str = "text", options: list | None = None) -> Answer:
        """写入 question 事件并阻塞等待操作者回答（串行化，同会话同时最多一个待答问题）。

        kind 与 options 随事件下发，前端据此决定渲染按钮还是输入框。
        问题带 qid 下发，作答可回传配对（陈旧作答拒收）。

        Write a question event and block until the operator answers (serialized: at most
        one pending question per session). kind and options travel with the event so the
        frontend can decide between buttons and a text input. The question carries a
        qid so answers can be paired (stale answers rejected).
        """
        # 串行化提问：同会话同时最多一个待答问题，避免并发子代理答非所问
        async with self._ask_lock:
            qid = "q_" + uuid4().hex[:12]
            self.pending_qid = qid
            await self.events.put(
                QuestionEvent(question=question, session_id=self.session_id,
                              kind=kind, options=options or [], qid=qid).emit()
            )
            self.awaiting_answer = True
            try:
                # 确认/澄清超时（agent.confirm_timeout_s，0=不限，与旧行为一致）：
                # 到期按「拒绝」回流（fail-closed），并下发 timeout 源的 answer 事件
                # 让前端当场收起问题卡，而不是让 question 悬在那里等回合结束。
                # Confirmation/clarify timeout (agent.confirm_timeout_s; 0 = no limit,
                # identical to the old behaviour): on expiry the answer flows back as
                # a rejection (fail-closed) and a timeout-sourced answer event is
                # emitted so the frontend folds the question card immediately instead
                # of leaving it dangling until the turn ends.
                timeout = config.settings.agent.confirm_timeout_s or None
                if timeout is None:
                    return await self.answers.get()
                try:
                    return await asyncio.wait_for(self.answers.get(), timeout)
                except asyncio.TimeoutError:
                    ans = Answer(text="", choice="no", reason="确认超时，未作答")
                    self.events.put_nowait(
                        AnswerEvent(qid=qid, text="", choice="no", source="timeout").emit()
                    )
                    return ans
            finally:
                self.awaiting_answer = False
                self.pending_qid = None
                # 清掉可能残留的迟到作答/弃题毒丸：ask 已返回，此刻队列里的任何东西
                # 都属于已结束的问题（answer 与 abandon 抢在同一轮时，毒丸会落在
                # 真回答后面没被消费），留给下一个 ask 只会开场即被吃掉。
                while not self.answers.empty():
                    self.answers.get_nowait()

    def abandon(self) -> bool:
        """弃题：正等待回答时向回答队列投弃题毒丸，解除 ask() 阻塞。

        不发 AnswerEvent —— 发起弃题的前端已自行清题，再发只会冒出一个怪答案块；
        不在等待回答时是 no-op，毒丸绝不残留给下一个 ask。

        Abandon the pending question: while an ask() is pending, put a poison-pill
        Answer into the queue to unblock it. No AnswerEvent is emitted (the frontend
        that initiated the abandonment already cleared its card; emitting one would
        only surface a stray answer block). A no-op when nothing is pending, so the
        pill can never leak into the next ask().

        Returns:
            是否真的投了毒丸（即正有提问在等待回答）。Whether a pill was actually
            delivered (i.e. a question was pending).
        """
        if not self.awaiting_answer:
            return False
        self.answers.put_nowait(Answer(text="", choice=None, reason=ABANDON_REASON))
        return True

    def answer(self, text: str, choice: str | None = None, *,
               qid: str | None = None, source: str | None = None) -> bool:
        """投递操作者回答到回答队列（由 /api/voice/answer 调用）。

        choice 为结构化选择（"yes" / "no"），由前端确认按钮回传。
        qid 与当前待答问题不符时拒绝投递并返回 False（防陈旧语音作答错配）；
        source 标记作答通道（typed / voice / button），随 AnswerEvent 下发可审计。

        Deliver the operator's answer into the answer queue (called by
        /api/voice/answer). choice is the structured selection ("yes" / "no")
        returned by the frontend's confirmation buttons. When qid does not match
        the pending question the delivery is rejected (returns False) so a stale
        voice answer cannot be mismatched. source marks the answering channel
        (typed / voice / button) and travels with the AnswerEvent for auditing.

        Returns:
            是否投递成功。Whether the delivery succeeded.
        """
        if qid is not None and self.pending_qid is not None and qid != self.pending_qid:
            return False
        self.answers.put_nowait(Answer(text=text, choice=choice))
        self.events.put_nowait(AnswerEvent(qid=self.pending_qid, text=text,
                                           choice=choice, source=source).emit())
        return True


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
        elif evt["type"] == "reasoning_delta":
            # 思考流转发（与 executor 路径一致，修复断链）
            # Forward the reasoning stream (consistent with the executor path;
            # fixes the broken chain).
            forwarded = from_llm_event(evt)
            if forwarded is not None:
                await events.put(forwarded)
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
        # 规范化历史种子：过滤合法消息并保证恒带 blocks（种子可能来自旧格式的
        # {role, content} 裸 dict —— content 包成单 text 块）。
        # Normalize the history seed: filter valid messages and guarantee blocks
        # (the seed may be legacy {role, content} bare dicts — wrap content as a
        # single text block).
        from core.orchestrator.blocks import make_block

        def _normalize(m: dict) -> dict:
            if m.get("blocks") is None:
                m = {**m, "blocks": [make_block("text", {"md": m.get("content") or ""})]
                     if m.get("content") else []}
            return m

        session.messages = [
            _normalize(m) for m in messages
            if isinstance(m, dict) and m.get("role") in ("user", "assistant")
            and isinstance(m.get("content"), str)
        ]
        # 确保当前用户消息在末尾（调用方可能只传历史）
        if not session.messages or session.messages[-1].get("role") != "user" or session.messages[-1].get("content") != text:
            session.append("user", text)
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
        clarified = await run_clarify(session, task)
        if clarified is None:
            # 操作者弃题（放弃本题）：与确认拒绝同一收束（done cancelled），
            # 绝不带着残缺参数往下执行。
            await events.put(TaskStateEvent(state="done", status="cancelled",
                                            summary="操作者放弃本题，任务取消").emit())
            await events.put(DoneEvent().emit())
            return
        task.params = clarified

    session.set_state(SessionState.CONFIRMING)
    conf = await confirm_if_needed(task, f"执行任务：{task.goal}", session)
    if not conf:
        # 拒绝理由（操作者自拟文本 / 超时标记）带进摘要，用户能看见「为什么取消」；
        # 策略 deny 与无通道路径 reason 为空 → 摘要与改造前逐字一致。
        # The refusal rationale (operator text / timeout marker) goes into the
        # summary so the user sees *why* the task was cancelled; policy-deny and
        # no-channel paths leave reason empty, so that summary is byte-identical
        # to the pre-change wording.
        detail = f"（{conf.reason}）" if conf.reason else ""
        await events.put(TaskStateEvent(state="done", status="cancelled",
                                        summary=f"操作者未确认{detail}，任务取消").emit())
        await events.put(DoneEvent().emit())
        return

    session.set_state(SessionState.EXECUTING)
    result = await execute_task(task, session, controller.token, events)
    # 任务后异步提取事实写长期记忆（不阻塞回复，失败静默）；
    # session 供提取看最近对话（解指代）并写溯源 origin（docs/designs/04）。
    if result.get("status") in ("done", "failed"):
        _spawn_bg(extract_and_store(task, result, get_facts_store(), session=session))
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
