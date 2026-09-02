# -*- coding: utf-8 -*-
"""上下文注入 — RAG 检索片段 + 长期事实 合并为系统提示片段。Context injection — merges RAG retrieval snippets + long-term facts into a system-prompt fragment."""
import re

from core.memory.facts import FactStore
from core.rag.retriever import rag_context

_KEYWORD_RE = re.compile(r"[a-z0-9_]+|[一-鿿]+")


def _keywords(query: str) -> list[str]:
    """从查询中提取关键词（≥2 字符的字母数字 / 中文片段）。Extract keywords from a query (alphanumeric / Chinese fragments of ≥2 characters).

    Args:
        query: 用户查询文本。User query text.

    Returns:
        小写关键词列表。The lowercased keyword list.
    """
    return [t for t in _KEYWORD_RE.findall(query.lower()) if len(t) >= 2]


def get_facts_store() -> FactStore:
    """返回容器持有的全局事实记忆存储（测试可 monkeypatch 本函数）。Return the global fact-memory store held by the container (tests may monkeypatch this function)."""
    from core.container import AppContext
    return AppContext.get().facts_store()


async def build_context(query: str, store: FactStore | None = None) -> str:
    """合并 RAG 检索 + 相关长期事实，返回注入文本（无则空字符串）。Merge RAG retrieval + relevant long-term facts, returning the injection text (empty string when nothing found).

    Args:
        query: 用户查询文本。User query text.
        store: 可选事实存储（默认取全局）。Optional fact store (defaults to the global one).

    Returns:
        注入系统提示的文本片段（可能为空）。The text fragment to inject into the system prompt (may be empty).
    """
    if store is None:
        store = get_facts_store()
    parts: list[str] = []
    try:
        ctx = await rag_context(query)
        if ctx:
            parts.append("【相关文档/环境】\n" + ctx)
    except Exception:
        pass
    try:
        facts = await store.search(_keywords(query))
        if facts:
            lines = [f"- {f['topic']}: {f['content']}" for f in facts]
            parts.append("【相关记忆】\n" + "\n".join(lines))
    except Exception:
        pass
    return "\n\n".join(parts)
