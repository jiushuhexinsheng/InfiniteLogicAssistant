# -*- coding: utf-8 -*-
"""编排 SSE 事件 — 类型化事件契约

pipeline / executor / voice 用这些模型构造事件 dict（`model_dump()`），
结构经 /api/voice/utter SSE 序列化；前端在 web/src/types.ts 手写对应类型
（SSE 不走 openapi，无法 openapi-typescript 自动生成）。

Orchestration SSE events — a typed event contract. pipeline / executor / voice
build event dicts with these models (`model_dump()`); the structure is serialized
over the /api/voice/utter SSE stream; the frontend hand-writes matching types in
web/src/types.ts (SSE does not go through openapi, so openapi-typescript cannot
generate them).
"""
from typing import Any, Literal

from pydantic import BaseModel


class _BaseEvent(BaseModel):
    """SSE 事件基类：提供统一的 emit() 序列化。

    Base class for SSE events: provides the unified emit() serialization.
    """

    def emit(self) -> dict:
        """事件 dict（剔除 None 默认字段，保持与历史事件结构一致）。

        Event dict (dropping None default fields to stay consistent with the
        historical event structure).
        """
        return self.model_dump(exclude_none=True)


class TaskStateEvent(_BaseEvent):
    """状态流转：understanding / notify / done。

    State transition: understanding / notify / done.
    """

    type: Literal["task_state"] = "task_state"
    state: str
    session_id: str = ""
    text: str | None = None       # state=notify：提示文本
    status: str | None = None     # state=done：done|failed|stopped|cancelled
    summary: str | None = None    # state=done：最终摘要
    steps: list[dict[str, Any]] | None = None  # state=done：执行步骤


class ContentDeltaEvent(_BaseEvent):
    """内容增量事件（SSE：content_delta）。Content delta event (SSE: content_delta)."""

    type: Literal["content_delta"] = "content_delta"
    text: str


class ReasoningDeltaEvent(_BaseEvent):
    """推理增量事件（SSE：reasoning_delta）。Reasoning delta event (SSE: reasoning_delta)."""

    type: Literal["reasoning_delta"] = "reasoning_delta"
    text: str


class UsageEvent(_BaseEvent):
    """用量事件（SSE：usage）。Usage event (SSE: usage)."""

    type: Literal["usage"] = "usage"
    usage: dict[str, Any] = {}    # OpenAI 风格 {prompt_tokens, completion_tokens, total_tokens}


class ToolStartEvent(_BaseEvent):
    """工具调用开始事件（SSE：tool_start）。Tool start event (SSE: tool_start)."""

    type: Literal["tool_start"] = "tool_start"
    name: str
    args: dict[str, Any] = {}


class ToolEndEvent(_BaseEvent):
    """工具调用结束事件（SSE：tool_end）。Tool end event (SSE: tool_end)."""

    type: Literal["tool_end"] = "tool_end"
    name: str
    status: str
    output: str


class QuestionOption(BaseModel):
    """询问选项：value 为机器可读取值，label 为展示文案。

    A question option: value is the machine-readable value, label is the display text.
    """

    value: str
    label: str


class QuestionEvent(_BaseEvent):
    """询问：前端回答走 POST /api/voice/answer。

    kind 决定前端渲染方式：
    - text      自由文本输入
    - choice    按 options 渲染按钮（原先的 confirm 即 choice + 确认/取消两项）
    - composite 按钮 + 输入框，任选其一即可提交

    A question: the frontend answers via POST /api/voice/answer. kind decides how the
    frontend renders it: text (free-form input), choice (buttons from options; the
    former confirm is just choice with confirm/cancel), or composite (buttons plus an
    input, either one suffices to submit).
    """

    type: Literal["question"] = "question"
    question: str
    session_id: str = ""
    kind: Literal["choice", "text", "composite"] = "text"
    options: list[QuestionOption] = []


class ErrorEvent(_BaseEvent):
    """错误事件（SSE：error）。Error event (SSE: error)."""

    type: Literal["error"] = "error"
    message: str


class DoneEvent(_BaseEvent):
    """结束事件（SSE：done）。Done event (SSE: done)."""

    type: Literal["done"] = "done"
