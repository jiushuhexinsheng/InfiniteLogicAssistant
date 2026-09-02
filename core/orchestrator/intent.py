# -*- coding: utf-8 -*-
"""意图判断 — 输入是「闲聊」还是「需要形成任务」

Intent judgment — whether the input is chit-chat or needs to form a task.
"""
import json
from dataclasses import dataclass

from core import config
from core.llm.client import get_llm_client
from core.logger import logger
from core.prompts import INTENT_SYSTEM

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
    """意图判断结果：type 为 chit_chat（闲聊）或 task（需要形成任务），summary 为一句话概括。

    Intent judgment result: type is "chit_chat" or "task", and summary is a
    one-sentence description of the user intent.
    """

    type: str  # "chit_chat" | "task"
    summary: str


# 记忆类陈述关键词：命中即确定性判为任务（不依赖 LLM 判断）
_MEMORY_HINTS = ("记住", "以后", "偏好", "我喜欢", "我希望", "帮我记", "默认", "记得")


async def judge_intent(text: str) -> IntentResult:
    """判断意图。记忆类陈述规则判为 task；其余走 LLM，失败/无工具兜底为 task。

    Judge the intent. Memory-like statements are classified as task by rule; the
    rest go to the LLM, falling back to task on failure or when no tool call is
    returned.
    """
    if any(h in text for h in _MEMORY_HINTS):
        logger.info("judge_intent(规则): {} → task", text)
        return IntentResult(type="task", summary=f"记住用户偏好：{text.strip()}")
    messages = [
        {"role": "system", "content": INTENT_SYSTEM},
        {"role": "user", "content": text},
    ]
    try:
        async for evt in get_llm_client().retry_stream_chat(
            messages, tools=[_JUDGE_TOOL], temperature=config.settings.agent.structured_temperature,
        ):
            if evt["type"] == "done":
                msg = evt["message"]
                tc = (msg.get("tool_calls") or [{}])[0]
                raw = tc.get("function", {}).get("arguments") or "{}"
                data = json.loads(raw) if isinstance(raw, str) else raw
                t = data.get("type") if data.get("type") in ("chit_chat", "task") else "task"
                logger.info("judge_intent(LLM): {} → {}", text, t)
                return IntentResult(type=t, summary=str(data.get("summary", text[:50])))
        logger.info("judge_intent(无工具兜底): {} → task", text)
        return IntentResult(type="task", summary=text[:50])
    except Exception as e:
        logger.warning("judge_intent 兜底为 task: {}", e)
        return IntentResult(type="task", summary=text[:50])
