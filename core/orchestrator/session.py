# -*- coding: utf-8 -*-
"""会话状态机与操作者通道

状态机：idle → understanding →(闲聊 chit_chat | 任务 forming_task)
→ clarifying → confirming → executing → reporting → idle；任何状态可 stopped / paused。
"""
import enum
import uuid
from typing import Any, Protocol


class SessionState(str, enum.Enum):
    IDLE = "idle"
    UNDERSTANDING = "understanding"
    CHIT_CHAT = "chit_chat"
    FORMING_TASK = "forming_task"
    CLARIFYING = "clarifying"
    CONFIRMING = "confirming"
    EXECUTING = "executing"
    REPORTING = "reporting"
    STOPPED = "stopped"
    PAUSED = "paused"


class OperatorChannel(Protocol):
    """操作者通道：由 server/语音层实现，用于提问与播报。"""

    async def ask(self, question: str) -> str: ...

    async def notify(self, text: str) -> None: ...


_ALLOWED: dict[SessionState, set[SessionState]] = {
    SessionState.IDLE: {SessionState.UNDERSTANDING, SessionState.CHIT_CHAT},
    SessionState.UNDERSTANDING: {SessionState.CHIT_CHAT, SessionState.FORMING_TASK, SessionState.IDLE},
    SessionState.CHIT_CHAT: {SessionState.IDLE},
    SessionState.FORMING_TASK: {SessionState.CLARIFYING, SessionState.CONFIRMING, SessionState.EXECUTING, SessionState.IDLE},
    SessionState.CLARIFYING: {SessionState.FORMING_TASK, SessionState.CONFIRMING, SessionState.EXECUTING, SessionState.IDLE},
    SessionState.CONFIRMING: {SessionState.EXECUTING, SessionState.IDLE},
    SessionState.EXECUTING: {SessionState.REPORTING, SessionState.IDLE, SessionState.STOPPED, SessionState.PAUSED},
    SessionState.REPORTING: {SessionState.IDLE},
    SessionState.STOPPED: {SessionState.IDLE, SessionState.PAUSED},
    SessionState.PAUSED: {SessionState.EXECUTING, SessionState.IDLE},
}


class Session:
    def __init__(self, session_id: str | None = None):
        self.id = session_id or uuid.uuid4().hex[:12]
        self.state: SessionState = SessionState.IDLE
        self.messages: list[dict] = []
        self.task: Any = None
        self.channel: OperatorChannel | None = None

    def set_state(self, new: SessionState) -> None:
        """状态迁移（stopped/paused 允许从任意状态进入）。"""
        if new in (SessionState.STOPPED, SessionState.PAUSED):
            self.state = new
            return
        if new not in _ALLOWED.get(self.state, set()):
            raise ValueError(f"非法状态迁移: {self.state.value} -> {new.value}")
        self.state = new

    def append(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})

    async def notify(self, text: str) -> None:
        if self.channel is not None:
            await self.channel.notify(text)

    async def ask(self, question: str) -> str:
        if self.channel is None:
            raise RuntimeError("会话无 OperatorChannel，无法向操作者提问")
        return await self.channel.ask(question)
