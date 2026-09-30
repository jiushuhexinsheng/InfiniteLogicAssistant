# -*- coding: utf-8 -*-
"""记忆工具 — 读取/检索/写入/删除长期事实（供 agent 与语音调用）

Memory tools — read / search / write / delete long-term facts (for agent and voice use)
"""
from core.memory.context import get_facts_store
from core.tools.base import tool


@tool("读取长期记忆（按主题）", risk="read")
async def memory_get(topic: str) -> str:
    """读取长期记忆（按主题）。Read long-term memory by topic.

    Args:
        topic: 记忆主题。Memory topic.

    Returns:
        记忆内容字符串；无相关记忆时返回 "无相关记忆"。Memory contents; "无相关记忆" when none found.
    """
    rows = await get_facts_store().get(topic)
    if not rows:
        return "无相关记忆"
    return "\n".join(f"- {r['topic']}: {r['content']}（来源 {r['source']}，{r['ts']}）" for r in rows)


@tool("写入长期记忆（同主题；等价复述只刷新时间，冲突则旧事实失效保留历史）", risk="write")
async def memory_put(topic: str, content: str, path: str = "") -> str:
    """写入长期记忆（ADD-only 协调语义，docs/designs/04 §3.1）。

    Write long-term memory (ADD-only reconcile semantics, docs/designs/04 §3.1).

    Args:
        topic: 记忆主题。Memory topic.
        content: 记忆内容。Memory content.
        path: 分层路径（偏好/习惯/项目/环境/其他，可空）。Hierarchy path (empty = unclassified).

    Returns:
        成功提示。Success message.
    """
    await get_facts_store().upsert(topic, content, source="voice", path=path)
    return f"已记住：{topic} → {content}"


@tool("按关键词检索长期记忆（带时间/路径/来源）", risk="read")
async def memory_search(query: str, path: str = "") -> str:
    """按关键词检索长期记忆（对话中实时核对/纠正既有记忆用）。

    Search long-term memory by keywords (for real-time checking/correction of existing
    memory mid-conversation).

    Args:
        query: 检索关键词。Search keywords.
        path: 可选路径过滤（如 偏好）。Optional path filter (e.g. 偏好).

    Returns:
        命中列表（topic/content/path/ts/source）；无命中返回 "无相关记忆"。Hits; "无相关记忆" when none.
    """
    rows = await get_facts_store().search([query], limit=10)
    if path:
        rows = [r for r in rows if r.get("path") == path]
    if not rows:
        return "无相关记忆"
    return "\n".join(
        f"- {(r['path'] + '/' if r.get('path') else '')}{r['topic']}: {r['content']}"
        f"（{r['ts']}，来源 {r['source']}）"
        for r in rows
    )


@tool("删除长期记忆（按主题硬删）", risk="write")
async def memory_delete(topic: str) -> str:
    """删除长期记忆（用户明确要求忘掉时调用；硬删不留痕）。

    Delete long-term memory (call when the user explicitly wants it forgotten; hard
    delete, no trace).

    Args:
        topic: 记忆主题。Memory topic.

    Returns:
        结果提示。Result message.
    """
    rows = await get_facts_store().get(topic)
    if not rows:
        return f"没有名为「{topic}」的记忆"
    await get_facts_store().delete(topic)
    return f"已删除：{topic}（{len(rows)} 条）"
