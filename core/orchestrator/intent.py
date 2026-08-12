# -*- coding: utf-8 -*-
"""意图判断 — 输入是「闲聊」还是「需要形成任务」"""
import json
from dataclasses import dataclass

from core.llm.client import get_llm_client
from core.logger import logger

_JUDGE_TOOL = {
    "type": "function",
    "function": {
        "name": "judge",
        "description": "判断用户输入是闲聊还是要形成任务执行",
        "parameters": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["chit_chat", "task"]},
                "summary": {"type": "string", "description": "一句话概括用户意图"},
            },
            "required": ["type", "summary"],
        },
    },
}


@dataclass
class IntentResult:
    type: str  # "chit_chat" | "task"
    summary: str


async def judge_intent(text: str) -> IntentResult:
    """判断意图。LLM 失败/无工具时兜底为 task。"""
    messages = [
        {"role": "system", "content": "判断用户输入意图，用 judge 工具返回：chit_chat=闲聊直接回复；task=需要形成任务执行。"},
        {"role": "user", "content": text},
    ]
    try:
        async for evt in get_llm_client().retry_stream_chat(messages, tools=[_JUDGE_TOOL]):
            if evt["type"] == "done":
                msg = evt["message"]
                tc = (msg.get("tool_calls") or [{}])[0]
                raw = tc.get("function", {}).get("arguments") or "{}"
                data = json.loads(raw) if isinstance(raw, str) else raw
                t = data.get("type") if data.get("type") in ("chit_chat", "task") else "task"
                return IntentResult(type=t, summary=str(data.get("summary", text[:50])))
        return IntentResult(type="task", summary=text[:50])
    except Exception as e:
        logger.warning("judge_intent 兜底为 task: {}", e)
        return IntentResult(type="task", summary=text[:50])
