# -*- coding: utf-8 -*-
"""意图判断 — 概括说法、判断复杂度、决定是否真的需要反问

不再区分「闲聊 / 任务」：每一轮都走同一条 ReAct 管线（工具常开，模型自己决定要不要
调用）。本模块只回答三个问题：

- summary：用户想干什么（一句话）；
- complexity：是否复杂到值得交给多智能体；
- ambiguous：是否真的没把握 —— 只有猜错会有实际代价时才反问，能合理假设就直接做。

Intent judging — summarise, gauge complexity, and decide whether a question is really
needed. There is no chat/task split any more: every turn runs the same ReAct pipeline
with tools always available. This module only answers: what does the user want, is it
complex enough for the multi-agent path, and is it genuinely unguessable (ask only
then; otherwise make a reasonable assumption and get on with it).
"""
import json
from dataclasses import dataclass, field
from typing import Any

from core import config
from core.llm.client import get_llm_client
from core.logger import logger
from core.prompts import INTENT_SYSTEM

_JUDGE_TOOL = {
    "type": "function",
    "function": {
        "name": "judge",
        "description": "概括用户意图、判断复杂度、判断是否真的需要反问",
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "一句话概括用户想干什么"},
                "complexity": {
                    "type": "string",
                    "enum": ["simple", "complex"],
                    "description": (
                        "simple=一句话能答/一两个工具调用就能完成；"
                        "complex=需要多步骤、多子任务或大量工具调用"
                    ),
                },
                "ambiguous": {
                    "type": "boolean",
                    "description": (
                        "只有完全没把握、且猜错会有实际代价（删错文件、改错项目等）才为 true；"
                        "能合理假设就为 false"
                    ),
                },
                "question": {"type": "string", "description": "ambiguous 为 true 时，要问用户的那一个关键问题"},
                "options": {
                    "type": "array",
                    "description": "可选：给用户的选择项（能枚举时给，否则留空走文本输入）",
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
            "required": ["summary", "complexity", "ambiguous"],
        },
    },
}


@dataclass
class IntentResult:
    """意图判断结果：概括 + 复杂度 + 是否真的需要反问。

    Intent result: summary, complexity, and whether a clarification question is really
    necessary (with that one question and its optional choices).
    """

    summary: str
    complexity: str = "simple"   # simple | complex
    ambiguous: bool = False
    question: str = ""
    options: list[dict] = field(default_factory=list)


def _parse_options(raw: Any) -> list[dict]:
    """把 LLM 给的选项规范化为 [{value, label}]（容忍纯字符串）。

    Normalise the LLM's options into [{value, label}] (plain strings tolerated).
    """
    out: list[dict] = []
    for entry in raw or []:
        if isinstance(entry, str) and entry.strip():
            out.append({"value": entry.strip(), "label": entry.strip()})
        elif isinstance(entry, dict):
            value = str(entry.get("value") or entry.get("label") or "").strip()
            if value:
                out.append({"value": value, "label": str(entry.get("label") or value)})
    return out


async def judge_intent(text: str) -> IntentResult:
    """判断意图：概括、复杂度、是否需要反问。任何失败都兜底为「照常执行」。

    Judge the intent: summary, complexity, and whether to ask. Any failure falls back
    to "just proceed" — a judging hiccup must never block the turn.

    Args:
        text: 用户原话。The user's utterance.

    Returns:
        意图判断结果。The intent result.
    """
    fallback = IntentResult(summary=text.strip()[:50] or text.strip())
    messages = [
        {"role": "system", "content": INTENT_SYSTEM},
        {"role": "user", "content": text},
    ]
    try:
        async for evt in get_llm_client().retry_stream_chat(
            messages, tools=[_JUDGE_TOOL], temperature=config.settings.agent.structured_temperature,
        ):
            if evt["type"] != "done":
                continue
            tc = (evt["message"].get("tool_calls") or [{}])[0]
            raw = tc.get("function", {}).get("arguments") or "{}"
            data = json.loads(raw) if isinstance(raw, str) else raw
            if not isinstance(data, dict):
                return fallback
            complexity = data.get("complexity")
            question = str(data.get("question") or "").strip()
            result = IntentResult(
                summary=str(data.get("summary") or "").strip() or fallback.summary,
                complexity=complexity if complexity in ("simple", "complex") else "simple",
                # 标了 ambiguous 却没给问题 = 问不出来，按不反问处理（否则卡在空问题前）。
                # ambiguous without a question cannot be asked: treat it as unambiguous.
                ambiguous=bool(data.get("ambiguous")) and bool(question),
                question=question,
                options=_parse_options(data.get("options")),
            )
            logger.info("judge_intent: {} → {} / {} / {}",
                        text, result.summary, result.complexity,
                        "ask" if result.ambiguous else "proceed")
            return result
        logger.info("judge_intent(无工具兜底): {}", text)
        return fallback
    except Exception as e:
        logger.warning("judge_intent 兜底: {}", e)
        return fallback
