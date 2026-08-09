# -*- coding: utf-8 -*-
"""duckduckgo 联网搜索"""
from core.config import cfg
from core.tools.base import tool


@tool("联网搜索网页，返回标题/链接/摘要")
def web_search(query: str) -> str:
    from duckduckgo_search import DDGS
    try:
        results = DDGS().text(query, max_results=cfg("tools.search_max_results", 5))
    except Exception as exc:
        return f"Error: {exc}"
    if not results:
        return "未找到结果"
    lines = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "")
        href = r.get("href", "")
        body = (r.get("body") or "")[:120]
        lines.append(f"{i}. {title}\n   {href}\n   {body}")
    return "\n".join(lines)
