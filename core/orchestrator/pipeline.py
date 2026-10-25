# -*- coding: utf-8 -*-
"""编排管线 — 一次输入 → 判断意图 →（必要时问一次）→ 执行 → 汇报

不再区分闲聊与任务：每一轮都是同一条 ReAct 管线（工具常开，由模型自己决定要不要
调用）。意图判断只负责三件事：概括、复杂度、是否真的需要反问 —— 只在完全没把握、
猜错有实际代价时问且只问一次。事件写进 asyncio.Queue，由 server 的 SSE 生成器消费；
ask() 抛出 question 事件后阻塞，等待 /api/voice/answer 投递回答（人类在环）。

Orchestration pipeline — one input → judge intent → (ask once only when genuinely
unguessable) → execute → report. There is no chat/task split: every turn is the same
ReAct pipeline with tools always available; the model decides whether to call them.
Intent judging only summarises, gauges complexity and decides whether one question is
really needed. Events go into an asyncio.Queue consumed by the SSE generator; ask()
blocks after emitting a question until /api/voice/answer delivers the answer.
"""
import asyncio
from datetime import datetime
from uuid import uuid4

from core import config
from core.logger import logger
from core.memory.context import get_facts_store
from core.memory.extract import extract_and_store
from core.orchestrator.control import PauseController, StopController
from core.orchestrator.events import (
    AnswerEvent, DoneEvent, QuestionEvent, TaskStateEvent,
)
from core.orchestrator.executor import execute_task
from core.orchestrator.intent import judge_intent
from core.orchestrator.session import ABANDON_REASON, Answer, OperatorChannel, Session, SessionState
from core.orchestrator.task import Task

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


async def run_pipeline(text: str, session: Session, events: asyncio.Queue,
                       controller: StopController, channel: OperatorChannel | None = None,
                       messages: list[dict] | None = None, mode: str = "chat",
                       pause: PauseController | None = None) -> None:
    """完整编排，产出事件（以 done 事件收尾）。channel 缺省用 SSE 队列通道。

    messages 为前端多轮历史种子（含当前用户消息）；缺省时把 text 记为当前用户消息。
    mode 仅为兼容旧前端保留，不参与任何分支。

    Full orchestration that emits events (ending with a done event). The channel
    defaults to the SSE queue channel. messages is the frontend multi-turn history
    seed (including the current user message); when absent, text is recorded as the
    current user message. mode survives only for legacy frontends and drives nothing.
    """
    del mode  # 旧前端的对话/任务模式已删除。The legacy chat/task mode is gone.
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
    logger.info("编排意图: {} → {}（{}）", text, intent.summary, intent.complexity)
    goal = text
    if intent.ambiguous and intent.question:
        # 只问一次：问完就把回答并进目标继续做，绝不进入多轮澄清循环。
        # Ask at most once: fold the answer into the goal and carry on — never a
        # multi-round clarification loop.
        session.set_state(SessionState.CLARIFYING)
        answer = await session.ask(
            intent.question,
            kind="choice" if intent.options else "text",
            options=intent.options,
        )
        extra = (answer.choice or answer.text or "").strip()
        if answer.reason == ABANDON_REASON or not extra:
            # 弃题/空回答：不以猜测继续。Abandoned or empty: never proceed on a guess.
            await events.put(TaskStateEvent(
                state="done", status="cancelled", summary="操作者未回答，本轮取消").emit())
            await events.put(DoneEvent().emit())
            return
        goal = f"{text}\n补充说明：{extra}"

    task = Task(
        id=uuid4().hex[:12], goal=goal, params={}, risk="read",
        complexity=intent.complexity, created=datetime.now().isoformat(),
    )
    session.task = task

    if controller.token.is_cancelled:
        # 判断/反问期间用户按了停止。Stopped while judging or asking.
        await events.put(TaskStateEvent(
            state="done", status="stopped", summary="已停止", steps=[]).emit())
        await events.put(DoneEvent().emit())
        return

    session.set_state(SessionState.EXECUTING)
    result = await execute_task(task, session, controller.token, events, pause=pause)
    # 任务后异步提取事实写长期记忆（不阻塞回复，失败静默）；
    # session 供提取看最近对话（解指代）并写溯源 origin（docs/designs/04）。
    if result.get("status") in ("done", "failed"):
        _spawn_bg(extract_and_store(task, result, get_facts_store(), session=session))

    session.set_state(SessionState.REPORTING)
    await events.put(TaskStateEvent(
        state="done", status=result["status"], summary=result["summary"], steps=result["steps"],
    ).emit())
    await events.put(DoneEvent().emit())
