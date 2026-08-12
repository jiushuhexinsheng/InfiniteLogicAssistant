# -*- coding: utf-8 -*-
"""任务形成 — 把意图结构化：goal / params / missing(要问操作者的问题) / risk"""
import json
import uuid
from dataclasses import dataclass, field

from core.llm.client import get_llm_client
from core.logger import logger
from core.orchestrator.intent import IntentResult

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
                    "type": "array", "items": {"type": "string"},
                    "description": "需要向操作者确认的缺失信息（写成自然语言问题）",
                },
                "risk": {"type": "string", "enum": ["read", "write", "exec"]},
            },
            "required": ["goal", "params", "missing", "risk"],
        },
    },
}


@dataclass
class Task:
    id: str
    goal: str
    params: dict = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    risk: str = "read"
    state: str = "queued"  # queued/planning/running/waiting_question/waiting_confirm/done/failed/stopped/paused


async def form_task(intent: IntentResult) -> Task:
    """用 LLM 结构化形成任务；失败兜底为纯 goal、无缺失。"""
    messages = [
        {"role": "system", "content": "根据用户意图形成结构化任务。missing 里列出需要向操作者确认的问题；risk 按操作判定：read只读/write写/exec执行任意命令。"},
        {"role": "user", "content": intent.summary},
    ]
    fallback = Task(id=uuid.uuid4().hex[:12], goal=intent.summary, params={}, missing=[], risk="read")
    try:
        async for evt in get_llm_client().retry_stream_chat(messages, tools=[_FORM_TOOL]):
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
                    missing=[str(m) for m in (data.get("missing") or [])],
                    risk=risk,
                )
        return fallback
    except Exception as e:
        logger.warning("form_task 兜底: {}", e)
        return fallback
