# -*- coding: utf-8 -*-
"""会话状态机与操作者通道

状态机：idle → understanding →(闲聊 chit_chat | 任务 forming_task)
→ clarifying → confirming → executing → reporting → idle；任何状态可 stopped。

Session state machine and operator channel. State machine: idle → understanding
→ (chit_chat | forming_task) → clarifying → confirming → executing → reporting →
idle; any state may transition to stopped.
"""
import enum
import uuid
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class Answer:
    """操作者对提问的回答。

    结构化确认的判定只看 choice（由前端按钮回传），text 仅承载自由文本；
    choice 为 None 表示操作者没有做出结构化选择。

    An operator's answer to a question.

    Structured confirmation only looks at choice (returned by frontend buttons);
    text carries free-form input only. A None choice means the operator made no
    structured selection.
    """

    text: str = ""
    choice: str | None = None  # "yes" | "no" | None（自由文本）


class SessionState(str, enum.Enum):
    """会话状态机枚举：idle → understanding →（chit_chat | forming_task）→ … → idle，可 stopped。

    Session state machine enum: idle → understanding → (chit_chat |
    forming_task) → … → idle; any state may transition to stopped.
    """

    IDLE = "idle"
    UNDERSTANDING = "understanding"
    CHIT_CHAT = "chit_chat"
    FORMING_TASK = "forming_task"
    CLARIFYING = "clarifying"
    CONFIRMING = "confirming"
    EXECUTING = "executing"
    REPORTING = "reporting"
    STOPPED = "stopped"


class OperatorChannel(Protocol):
    """操作者通道：由 server/语音层实现，用于提问与播报。

    Operator channel: implemented by the server/voice layer for asking questions
    and announcing messages.
    """

    async def ask(self, question: str, *, kind: str = "clarify") -> Answer: ...

    async def notify(self, text: str) -> None: ...


_ALLOWED: dict[SessionState, set[SessionState]] = {
    SessionState.IDLE: {SessionState.UNDERSTANDING, SessionState.CHIT_CHAT},
    SessionState.UNDERSTANDING: {SessionState.CHIT_CHAT, SessionState.FORMING_TASK, SessionState.IDLE},
    SessionState.CHIT_CHAT: {SessionState.IDLE},
    SessionState.FORMING_TASK: {SessionState.CLARIFYING, SessionState.CONFIRMING, SessionState.EXECUTING, SessionState.IDLE},
    SessionState.CLARIFYING: {SessionState.FORMING_TASK, SessionState.CONFIRMING, SessionState.EXECUTING, SessionState.IDLE},
    SessionState.CONFIRMING: {SessionState.EXECUTING, SessionState.IDLE},
    SessionState.EXECUTING: {SessionState.REPORTING, SessionState.IDLE, SessionState.STOPPED},
    SessionState.REPORTING: {SessionState.IDLE},
    SessionState.STOPPED: {SessionState.IDLE},
}


class Session:
    """会话：维护状态机、消息历史、当前任务与操作者通道。

    Session: holds the state machine, message history, current task, and the
    operator channel.
    """

    def __init__(self, session_id: str | None = None):
        """初始化会话：可指定会话 ID，缺省生成短随机 ID。

        Initialize a session; a session id may be supplied, otherwise a short
        random id is generated.
        """
        self.id = session_id or uuid.uuid4().hex[:12]
        self.state: SessionState = SessionState.IDLE
        self.messages: list[dict] = []
        self.task: Any = None
        self.channel: OperatorChannel | None = None

    def set_state(self, new: SessionState) -> None:
        """状态迁移（stopped 允许从任意状态进入）。

        State transition (stopped is allowed from any state).
        """
        if new == SessionState.STOPPED:
            self.state = new
            return
        if new not in _ALLOWED.get(self.state, set()):
            raise ValueError(f"非法状态迁移: {self.state.value} -> {new.value}")
        self.state = new

    def append(self, role: str, content: str) -> None:
        """追加一条消息到会话历史。Append a message to the session history."""
        self.messages.append({"role": role, "content": content})

    def summary(self, max_messages: int = 8) -> list[dict]:
        """返回最近 N 条消息，供上下文注入。

        Return the most recent N messages for context injection.
        """
        return self.messages[-max_messages:]

    async def notify(self, text: str) -> None:
        """通过操作者通道播报提示文本（无通道时静默忽略）。

        Notify the operator through the channel (silently ignored when there is
        no channel).
        """
        if self.channel is not None:
            await self.channel.notify(text)

    async def ask(self, question: str, *, kind: str = "clarify") -> Answer:
        """向操作者提问并等待回答；无通道时抛 RuntimeError。

        kind 区分提问类型：clarify（澄清，自由文本作答）或 confirm（确认，结构化选择）。

        Ask the operator a question and wait for the answer; raise RuntimeError
        when there is no channel. kind distinguishes the question type: clarify
        (free-form answer) or confirm (structured choice).
        """
        if self.channel is None:
            raise RuntimeError("会话无 OperatorChannel，无法向操作者提问")
        return await self.channel.ask(question, kind=kind)
