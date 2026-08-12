# -*- coding: utf-8 -*-
"""记忆工具 — 读取/写入长期事实（供 agent 与语音调用）"""
from core.memory.context import get_facts_store
from core.tools.base import tool


@tool("读取长期记忆（按主题）", risk="read")
async def memory_get(topic: str) -> str:
    rows = await get_facts_store().get(topic)
    if not rows:
        return "无相关记忆"
    return "\n".join(f"- {r['topic']}: {r['content']}（来源 {r['source']}，{r['ts']}）" for r in rows)


@tool("写入长期记忆（同主题覆盖）", risk="write")
async def memory_put(topic: str, content: str) -> str:
    await get_facts_store().upsert(topic, content, source="voice")
    return f"已记住：{topic} → {content}"
