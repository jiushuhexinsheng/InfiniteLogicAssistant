# -*- coding: utf-8 -*-
"""任务后事实提取 — LLM 结构化输出 facts → FactStore（失败静默，不阻塞主流程）。Post-task fact extraction — LLM structured-output facts → FactStore (failures are silent and never block the main flow)."""
import json

from core import config
from core.llm.client import get_llm_client
from core.logger import logger
from core.memory.facts import FactStore
from core.orchestrator.task import Task
from core.prompts import EXTRACT_FACTS_SYSTEM

_FACTS_TOOL = {
    "type": "function",
    "function": {
        "name": "extract_facts",
        "description": "从任务执行中提取值得长期记住的事实",
        "parameters": {
            "type": "object",
            "properties": {
                "facts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "topic": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["topic", "content"],
                    },
                },
            },
            "required": ["facts"],
        },
    },
}


async def extract_and_store(task: Task, result: dict, store: FactStore) -> None:
    """任务结束后提取用户事实写入记忆；非 done/failed 或 LLM 失败时静默跳过。Extract user facts after a task finishes and persist them to memory; silently skip when the task is not done/failed or the LLM call fails.

    Args:
        task: 已完成的任务。The finished task.
        result: 任务执行结果 dict（含 status / summary / steps）。The task result dict (with status / summary / steps).
        store: 事实存储。The fact store.
    """
    if not result or result.get("status") not in ("done", "failed"):
        return
    messages = [
        {"role": "system", "content": EXTRACT_FACTS_SYSTEM},
        {"role": "user", "content": f"任务：{task.goal}\n结果：{result.get('summary', '')}\n步骤：{json.dumps((result.get('steps') or [])[:5], ensure_ascii=False)}"},
    ]
    try:
        async for evt in get_llm_client().retry_stream_chat(
            messages, tools=[_FACTS_TOOL], temperature=config.settings.agent.structured_temperature,
        ):
            if evt["type"] == "done":
                msg = evt["message"]
                tc = (msg.get("tool_calls") or [{}])[0]
                raw = tc.get("function", {}).get("arguments") or "{}"
                data = json.loads(raw) if isinstance(raw, str) else raw
                for f in data.get("facts") or []:
                    topic = str(f.get("topic") or "").strip()
                    content = str(f.get("content") or "").strip()
                    if topic and content:
                        await store.upsert(topic, content, source=f"task:{task.id}")
                return
    except Exception as e:
        logger.warning("extract_and_store 失败: {}", e)
