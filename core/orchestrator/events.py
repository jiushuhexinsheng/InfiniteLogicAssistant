# -*- coding: utf-8 -*-
"""编排 SSE 事件 — 类型化事件契约

pipeline / executor / voice 用这些模型构造事件 dict（`model_dump()`），
结构经 /api/voice/utter SSE 序列化；前端在 web/src/types.ts 手写对应类型
（SSE 不走 openapi，无法 openapi-typescript 自动生成）。
"""
from typing import Any, Literal

from pydantic import BaseModel


class _BaseEvent(BaseModel):
    def emit(self) -> dict:
        """事件 dict（剔除 None 默认字段，保持与历史事件结构一致）。"""
        return self.model_dump(exclude_none=True)


class TaskStateEvent(_BaseEvent):
    """状态流转：understanding / notify / done。"""

    type: Literal["task_state"] = "task_state"
    state: str
    session_id: str = ""
    text: str | None = None       # state=notify：提示文本
    status: str | None = None     # state=done：done|failed|stopped|cancelled
    summary: str | None = None    # state=done：最终摘要
    steps: list[dict[str, Any]] | None = None  # state=done：执行步骤


class ContentDeltaEvent(_BaseEvent):
    type: Literal["content_delta"] = "content_delta"
    text: str


class ReasoningDeltaEvent(_BaseEvent):
    type: Literal["reasoning_delta"] = "reasoning_delta"
    text: str


class UsageEvent(_BaseEvent):
    type: Literal["usage"] = "usage"
    usage: dict[str, Any] = {}    # OpenAI 风格 {prompt_tokens, completion_tokens, total_tokens}


class ToolStartEvent(_BaseEvent):
    type: Literal["tool_start"] = "tool_start"
    name: str
    args: dict[str, Any] = {}


class ToolEndEvent(_BaseEvent):
    type: Literal["tool_end"] = "tool_end"
    name: str
    status: str
    output: str


class QuestionEvent(_BaseEvent):
    """澄清/确认问题：前端回答走 POST /api/voice/answer。"""

    type: Literal["question"] = "question"
    question: str
    session_id: str = ""


class ErrorEvent(_BaseEvent):
    type: Literal["error"] = "error"
    message: str


class DoneEvent(_BaseEvent):
    type: Literal["done"] = "done"
