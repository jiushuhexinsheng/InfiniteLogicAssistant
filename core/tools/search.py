# -*- coding: utf-8 -*-
"""duckduckgo 联网搜索（无 key；依赖网络，失败给出可操作提示）"""
from core.config import cfg
from core.tools.base import tool


def _describe_error(exc: Exception) -> str:
    """把搜索异常转成可操作的中文提示（保留原始详情）。"""
    return (
        f"联网搜索失败（{type(exc).__name__}）。请检查网络连接；"
        f"duckduckgo 偶发限流，可稍后重试。详情: {exc}"
    )


@tool("联网搜索网页，返回标题/链接/摘要")
def web_search(query: str) -> str:
    from duckduckgo_search import DDGS
    try:
        results = DDGS().text(query, max_results=cfg("tools.search_max_results", 5))
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
