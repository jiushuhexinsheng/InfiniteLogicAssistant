# -*- coding: utf-8 -*-
"""任务形成 — 把意图结构化：goal / params / missing(要问操作者的问题) / risk

Task formation — structures the intent into goal / params / missing (questions
to ask the operator) / risk.
"""
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core import config
from core.llm.client import get_llm_client
from core.logger import logger
from core.orchestrator.intent import IntentResult
from core.prompts import FORM_TASK_SYSTEM

_FORM_TOOL = {
    "type": "function",
    "function": {
        "name": "form_task",
        "description": "把用户任务意图转成结构化任务",
        "parameters": {
            "type": "object",
            "properties": {
                "goal": {"type": "string", "description": "任务目标（一句话）"},
                "params": {"type": "object", "description": "已明确的关键参数键值"},
                "missing": {
                    "type": "array",
                    "description": "需要向操作者确认的缺失信息",
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string", "description": "要问操作者的问题"},
                            "type": {
                                "type": "string",
                                "enum": ["text", "choice", "composite"],
                                "description": "作答方式：text 自由文本 / choice 从选项选 / composite 选项加补充说明",
                            },
                            "options": {
                                "type": "array",
                                "description": "type 为 choice 或 composite 时必填",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "value": {"type": "string"},
                                        "label": {"type": "string"},
                                    },
                                    "required": ["value", "label"],
                                },
                            },
                        },
                        "required": ["question"],
                    },
                },
                "risk": {"type": "string", "enum": ["read", "write", "exec"]},
            },
            "required": ["goal", "params", "missing", "risk"],
        },
    },
}


@dataclass
class MissingItem:
    """任务缺失信息的一条：问题文本 + 期望的作答方式。

    一条缺失信息由 LLM 产出，并决定前端渲染成输入框还是按钮。
    type 为 "choice"/"composite" 时 options 必须非空，否则无法作答（解析时降级为 text）。

    One piece of missing task information: the question text plus how it should be
    answered. Produced by the LLM and deciding whether the frontend renders an input or
    buttons. When type is "choice"/"composite", options must be non-empty or the question
    is unanswerable (the parser degrades it to text).
    """

    question: str
    type: str = "text"  # text | choice | composite
    options: list[dict] = field(default_factory=list)


@dataclass
class Task:
    """结构化任务：目标、参数、缺失信息、风险与执行状态。

    Structured task: goal, params, missing information, risk, and execution state.
    """

    id: str
    goal: str
    params: dict = field(default_factory=dict)
    missing: list[MissingItem] = field(default_factory=list)
    risk: str = "read"
    state: str = "queued"  # queued/planning/running/waiting_question/waiting_confirm/done/failed/stopped
    # 创建时间（ISO 字符串）：任务库存档用。直接构造的 Task 缺省为空串。
    # Creation timestamp (ISO string) for the task library; empty when constructed directly.
    created: str = ""


_VALID_TYPES = ("text", "choice", "composite")


def parse_missing(raw: Any) -> list[MissingItem]:
    """把 LLM 产出的 missing 解析为 MissingItem 列表，带三条容错。

    容错（form_task 依赖 LLM 输出，schema 不保证被遵守）：
    1. 元素是字符串 → 当作 text 类问题
    2. type 缺失或非法 → text
    3. type 为 choice/composite 但 options 为空 → 降级为 text（没有选项无法作答）

    Parse the LLM-produced missing list into MissingItems with three fallbacks. form_task
    depends on LLM output and the schema is not guaranteed to be honoured, so: (1) a plain
    string element becomes a text question; (2) a missing or invalid type becomes text;
    (3) a choice/composite with no options degrades to text, since it cannot be answered.

    Args:
        raw: LLM 产出的 missing 原始值。The raw missing value produced by the LLM.

    Returns:
        MissingItem 列表（问题为空的条目被跳过）。The list of MissingItems (entries with an empty question are skipped).
    """
    items: list[MissingItem] = []
    for entry in raw or []:
        question: str
        kind: str
        options: list[dict]
        if isinstance(entry, str):
            question, kind, options = entry.strip(), "text", []
        elif isinstance(entry, dict):
            question = str(entry.get("question") or "").strip()
            raw_type = entry.get("type")
            kind = raw_type if raw_type in _VALID_TYPES else "text"
            options = [
                {"value": str(o.get("value", "")), "label": str(o.get("label", ""))}
                for o in (entry.get("options") or [])
                if isinstance(o, dict)
            ]
        else:
            continue
        if not question:
            continue
        if kind in ("choice", "composite") and not options:
            kind = "text"  # 没有选项的选择题无法作答 / an optionless multiple-choice is unanswerable
        items.append(MissingItem(question=question, type=kind, options=options))
    return items


async def form_task(intent: IntentResult, confirmed: dict | None = None) -> Task:
    """用 LLM 结构化形成任务；失败兜底为纯 goal、无缺失。

    confirmed 为澄清阶段已确认的参数键值，单独作为结构化信息呈现（不污染 goal）。

    Form the task structurally with the LLM; on failure, fall back to a bare goal
    with no missing items. confirmed holds the parameter key-values already
    confirmed during clarification and is presented as separate structured info
    (without polluting the goal).
    """
    user = intent.summary
    if confirmed:
        user += f"\n已确认信息：{json.dumps(confirmed, ensure_ascii=False)}"
    messages = [
        {"role": "system", "content": FORM_TASK_SYSTEM},
        {"role": "user", "content": user},
    ]
    fallback = Task(id=uuid.uuid4().hex[:12], goal=intent.summary, params={}, missing=[], risk="read",
                    created=datetime.now().isoformat())
    try:
        async for evt in get_llm_client().retry_stream_chat(
            messages, tools=[_FORM_TOOL], temperature=config.settings.agent.structured_temperature,
        ):
            if evt["type"] == "done":
                msg = evt["message"]
                tc = (msg.get("tool_calls") or [{}])[0]
                raw = tc.get("function", {}).get("arguments") or "{}"
                data = json.loads(raw) if isinstance(raw, str) else raw
                risk = data.get("risk") if data.get("risk") in ("read", "write", "exec") else "read"
                return Task(
                    id=uuid.uuid4().hex[:12],
                    goal=str(data.get("goal") or intent.summary),
                    params=dict(data.get("params") or {}),
                    missing=parse_missing(data.get("missing")),
                    risk=risk,
                    created=datetime.now().isoformat(),
                )
        return fallback
    except Exception as e:
        logger.warning("form_task 兜底: {}", e)
        return fallback
