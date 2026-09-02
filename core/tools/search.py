# -*- coding: utf-8 -*-
"""duckduckgo 联网搜索（无 key；依赖网络，失败给出可操作提示）

duckduckgo web search (no API key; network-dependent, actionable hints on failure)
"""
from core import config
from core.tools.base import tool


def _describe_error(exc: Exception) -> str:
    """把搜索异常转成可操作的中文提示（保留原始详情）。Convert a search exception into an actionable Chinese hint (keeping the original detail).

    Args:
        exc: 捕获的异常。Caught exception.

    Returns:
        中文提示字符串。Chinese hint string.
    """
    return (
        f"联网搜索失败（{type(exc).__name__}）。请检查网络连接；"
        f"duckduckgo 偶发限流，可稍后重试。详情: {exc}"
    )


@tool("联网搜索网页，返回标题/链接/摘要")
def web_search(query: str) -> str:
    """联网搜索网页，返回 标题/链接/摘要 列表。Search the web, returning title/link/summary entries.

    Args:
        query: 搜索关键词。Search query.

    Returns:
        结果列表字符串；未找到时返回 "未找到结果"。Formatted results; "未找到结果" when nothing found.
    """
    from duckduckgo_search import DDGS
    try:
        results = DDGS().text(query, max_results=config.settings.tools.search_max_results)
    except Exception as exc:
        return _describe_error(exc)
    if not results:
        return "未找到结果"
    lines = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "")
        href = r.get("href", "")
        body = (r.get("body") or "")[:120]
        lines.append(f"{i}. {title}\n   {href}\n   {body}")
    return "\n".join(lines)
