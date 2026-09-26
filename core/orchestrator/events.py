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

    新增可选字段一律默认 None（emit 的 exclude_none 下不下发），
    保证旧前端对事件形状零感知 —— 协议只增不改。

    Base class for SSE events: provides the unified emit() serialization.
    New optional fields default to None (dropped by exclude_none in emit), so
    legacy frontends see an unchanged event shape — the protocol is additive only.
    """

    turn_id: str | None = None   # 所属回合（一次用户话语→一次编排运行→done）

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
    """工具调用开始事件（SSE：tool_start）。Tool start event (SSE: tool_start).

    call_id 与 ToolEndEvent 配对（同一工具调用的两次事件）；
    agent 标记归属（main / coordinator / sub:<type>，多智能体事件前传用）。
    call_id pairs with ToolEndEvent (the two events of one tool call); agent
    marks ownership (main / coordinator / sub:<type>) for multi-agent attribution.
    """

    type: Literal["tool_start"] = "tool_start"
    name: str
    args: dict[str, Any] = {}
    call_id: str | None = None
    agent: str | None = None


class ToolEndEvent(_BaseEvent):
    """工具调用结束事件（SSE：tool_end）。Tool end event (SSE: tool_end).

    output 为预览（截断至 PREVIEW_LEN）；truncated/full 长度信息随事件下发，
    供前端块协议还原「截没截」。output is a preview (truncated to PREVIEW_LEN);
    truncated / output_len travel with the event so the frontend block protocol
    can tell whether truncation happened.
    """

    type: Literal["tool_end"] = "tool_end"
    name: str
    status: str
    output: str
    call_id: str | None = None
    agent: str | None = None
    truncated: bool | None = None
    output_len: int | None = None


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
    # 问题 ID：问答配对与陈旧作答拒收（/api/voice/answer 携带 qid 校验）。
    # Question ID: pairs answers with questions and rejects stale answers.
    qid: str | None = None


class AnswerEvent(_BaseEvent):
    """操作员作答事件（SSE：answer）— 作答入块、语音可审计。

    source 标记作答通道：typed（键盘）/ voice（语音）/ button（选项按钮）。

    Operator answer event (SSE: answer) — answers become blocks, voice answers
    are auditable. source marks the channel: typed / voice / button.
    """

    type: Literal["answer"] = "answer"
    qid: str | None = None
    text: str = ""
    choice: str | None = None
    source: str | None = None


class BlockEvent(_BaseEvent):
    """离散消息块直通事件（SSE：block）— image/file/ext:* 等新块类型即插即用。

    block 为消息块协议的块 dict（信封 + payload，见 core/orchestrator/blocks.py）。

    Discrete message-block passthrough event (SSE: block) — lets new block types
    (image / file / ext:*) plug in without touching the page. block carries a
    message-block-protocol dict (envelope + payload, see core/orchestrator/blocks.py).
    """

    type: Literal["block"] = "block"
    block: dict[str, Any] = {}


class ErrorEvent(_BaseEvent):
    """错误事件（SSE：error）。Error event (SSE: error)."""

    type: Literal["error"] = "error"
    message: str


class DoneEvent(_BaseEvent):
    """结束事件（SSE：done）。Done event (SSE: done)."""

    type: Literal["done"] = "done"


def from_llm_event(evt: dict) -> dict | None:
    """LLM 流事件 dict → 编排 SSE 事件 dict（统一产出口径）。

    LLM 层（core/llm/stream.py）产出协议无关事件 dict，此前 executor/pipeline
    把原始 dict 直接入队（与 Pydantic .emit() 口径混用）。本适配器把可直通的
    事件包装为类型化事件；tool_call_delta / done 由执行层自行编排（返回 None）。

    Convert an LLM-stream event dict into an orchestration SSE event dict (single
    emission convention). The LLM layer (core/llm/stream.py) yields
    protocol-agnostic event dicts; executor/pipeline used to enqueue them raw
    (mixing conventions with Pydantic .emit()). This adapter wraps pass-through
    events as typed events; tool_call_delta / done are orchestrated by the
    execution layer (returns None).

    Returns:
        编排事件 dict；不可直通的事件返回 None。An orchestration event dict, or
        None for events the execution layer handles itself.
    """
    t = evt.get("type")
    if t == "content_delta":
        return ContentDeltaEvent(text=evt.get("text", "")).emit()
    if t == "reasoning_delta":
        return ReasoningDeltaEvent(text=evt.get("text", "")).emit()
    if t == "usage":
        return UsageEvent(usage=evt.get("usage") or {}).emit()
    return None
