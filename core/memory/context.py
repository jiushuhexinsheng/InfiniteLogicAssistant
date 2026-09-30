# -*- coding: utf-8 -*-
"""上下文注入 — RAG 检索片段 + 长期事实 合并为系统提示片段。Context injection — merges RAG retrieval snippets + long-term facts into a system-prompt fragment."""
import re

from core.memory.facts import FactStore

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


async def build_context_with_sources(query: str, store: FactStore | None = None) -> tuple[str, list[dict]]:
    """合并 RAG 检索 + 相关长期事实，返回 (注入文本, RAG 命中列表)。

    命中列表供主执行路径发 `sources` 块（docs/designs/05 §3.2 引用溯源）；
    RAG 段为编号注入（`[n] 标题 (path)`），rerank 档位见 `rag.rerank`。
    记忆注入有界（docs/designs/04 §3.2）：top-k + 字符预算双闸，每行带日期。

    Merge RAG retrieval + relevant long-term facts, returning (injection text,
    RAG hits). The hits feed the `sources` block on the main execution path
    (docs/designs/05 §3.2 citation provenance); the RAG section is numbered
    (`[n] title (path)`), rerank tier via `rag.rerank`. Memory injection is bounded
    (docs/designs/04 §3.2): top-k + character budget, each line dated.

    Args:
        query: 用户查询文本。User query text.
        store: 可选事实存储（默认取全局）。Optional fact store (defaults to the global one).

    Returns:
        (注入文本, RAG 命中)。(injection text, RAG hits).
    """
    from core import config
    from core.rag.retriever import format_hits, rerank as rerank_fn, retrieve

    if store is None:
        store = get_facts_store()
    parts: list[str] = []
    sources: list[dict] = []
    try:
        ragcfg = config.settings.rag
        want_rerank = ragcfg.rerank == "llm"
        fetch_n = ragcfg.rerank_candidates if want_rerank else ragcfg.rerank_top_k
        hits = await retrieve(query, top_k=fetch_n)
        if hits and want_rerank:
            hits = await rerank_fn(query, hits, ragcfg.rerank_top_k)
        else:
            hits = hits[:ragcfg.rerank_top_k]
        ctx = format_hits(hits)
        if ctx:
            parts.append("【相关文档/环境】\n" + ctx)
            sources = hits
    except Exception:
        pass
    try:
        mem = config.settings.memory
        facts = await store.search(_keywords(query), limit=mem.inject_top_k)
        budget = mem.inject_max_chars
        lines: list[str] = []
        used = 0
        for f in facts:
            prefix = f"{f['path']}/" if f.get("path") else ""
            line = f"- {prefix}{f['topic']}: {f['content']}（{str(f.get('ts') or '')[:10]}）"
            if lines and used + len(line) > budget:
                break  # 预算截断：宁缺勿滥，第一条至少放进。Budget cut: the first line always fits.
            lines.append(line)
            used += len(line)
        if lines:
            parts.append("【相关记忆】\n" + "\n".join(lines))
    except Exception:
        pass
    return "\n\n".join(parts), sources


async def build_context(query: str, store: FactStore | None = None) -> str:
    """合并 RAG 检索 + 相关长期事实，返回注入文本（无则空字符串）。

    只需要文本的调用方（多智能体协调者等）用本入口；需要 RAG 命中做引用溯源的
    主执行路径用 `build_context_with_sources`。

    Merge RAG retrieval + relevant long-term facts, returning the injection text
    (empty when nothing found). Text-only callers (the multi-agent coordinator etc.)
    use this entry; the main execution path that needs RAG hits for citation
    provenance uses `build_context_with_sources`.

    Args:
        query: 用户查询文本。User query text.
        store: 可选事实存储（默认取全局）。Optional fact store (defaults to the global one).

    Returns:
        注入系统提示的文本片段（可能为空）。The text fragment to inject into the system prompt (may be empty).
    """
    text, _ = await build_context_with_sources(query, store)
    return text
