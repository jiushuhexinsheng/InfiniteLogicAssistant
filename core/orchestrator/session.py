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
from datetime import datetime
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

    async def ask(self, question: str, *, kind: str = "text", options: list | None = None) -> Answer: ...

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

    def append(self, role: str, content: str, blocks: list[dict] | None = None,
               ts: str | None = None, turn_id: str = "") -> None:
        """追加一条消息到会话历史。

        blocks 缺省时以 content 为源生成单 text 块（消息恒带 blocks）；
        content 是纯文本投影（由 text_projection 从块单向生成），
        供 LLM 回喂降级与摘要取用。

        Append a message to the session history. When blocks is omitted, a single
        text block is derived from content (messages always carry blocks). content
        is the plain-text projection (generated one-way from blocks via
        text_projection) for LLM feed fallback and summaries.
        """
        if blocks is None:
            from core.orchestrator.blocks import make_block
            blocks = [make_block("text", {"md": content})] if content else []
        self.messages.append({
            "role": role,
            "content": content,
            "blocks": blocks,
            "ts": ts or datetime.now().isoformat(),
            "turn_id": turn_id,
        })

    def append_block(self, role: str, block: dict) -> None:
        """向当前回合的末条消息追加一个块（tool/thinking/answer 均走这里）。

        末条消息角色不匹配或无消息时新建消息；content 投影同步重算。
        工具行不再产生独立 "tool" 消息。

        Append a block to the last message of the current turn (tool / thinking /
        answer all go through here). A new message is started when the last one is
        missing or has a different role; the content projection is recomputed.
        Tool calls no longer create standalone "tool" messages.
        """
        from core.orchestrator.blocks import text_projection

        if self.messages and self.messages[-1].get("role") == role:
            msg = self.messages[-1]
            if msg.get("blocks") is None:
                msg["blocks"] = []
            msg["blocks"].append(block)
            msg["content"] = text_projection(msg["blocks"])
        else:
            self.messages.append({
                "role": role,
                "content": text_projection([block]),
                "blocks": [block],
                "ts": block.get("ts") or datetime.now().isoformat(),
                "turn_id": block.get("turn_id", ""),
            })

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

    async def ask(self, question: str, *, kind: str = "text", options: list | None = None) -> Answer:
        """向操作者提问并等待回答；无通道时抛 RuntimeError。

        kind 决定前端渲染方式（text 自由文本 / choice 按选项出按钮 / composite 两者并存），
        options 供 choice 与 composite 使用。

        Ask the operator a question and wait for the answer; raise RuntimeError when there
        is no channel. kind decides how the frontend renders it (text for free input,
        choice for option buttons, composite for both); options is used by choice and
        composite.
        """
        if self.channel is None:
            raise RuntimeError("会话无 OperatorChannel，无法向操作者提问")
        return await self.channel.ask(question, kind=kind, options=options)
