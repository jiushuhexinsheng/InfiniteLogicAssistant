# -*- coding: utf-8 -*-
"""duckduckgo 联网搜索（无 key；依赖网络，失败给出可操作提示）

依赖已改名为 `ddgs`（旧名 duckduckgo_search 每次调用都发 RuntimeWarning 并已停维护）：
优先 import ddgs，装不上时回退旧包并压掉改名警告。

duckduckgo web search (no API key; network-dependent, actionable hints on failure).
The dependency was renamed to `ddgs` (the old duckduckgo_search name emits a
RuntimeWarning on every call and is no longer maintained): prefer importing ddgs,
fall back to the old package with the rename warning suppressed.
"""
from core import config
from core.tools.base import tool


def _load_ddgs():
    """加载 DDGS 类：ddgs 优先，旧包兜底（压掉改名警告）。Load the DDGS class: ddgs first, old package as fallback."""
    try:
        from ddgs import DDGS  # 新包名 / renamed package
        return DDGS
    except ImportError:
        import warnings

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=r".*renamed to `ddgs`.*")
            from duckduckgo_search import DDGS  # 旧包兜底 / legacy fallback
        return DDGS


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
    DDGS = _load_ddgs()
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
