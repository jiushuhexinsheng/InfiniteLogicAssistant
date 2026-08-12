# -*- coding: utf-8 -*-
"""RAG 检索 — 关键词命中打分（纯 Python，无外部依赖）"""
import re
import sqlite3

from core.rag import INDEX_DB

_TOKEN_RE = re.compile(r"[a-z0-9_]+|[一-鿿]+")


def _tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if len(t) >= 2]


async def retrieve(query: str, top_k: int = 5) -> list[dict]:
    """按关键词命中数打分，返回 top-k 块（[{path, section, text, score}]）。"""
    tokens = _tokenize(query)
    if not tokens:
        return []
    with sqlite3.connect(str(INDEX_DB)) as conn:
        rows = conn.execute("SELECT path, section, text FROM chunks").fetchall()
    scored = []
    for path, section, text in rows:
        low = text.lower()
        score = sum(1 for t in tokens if t in low)
        if score:
            scored.append({"path": path, "section": section, "text": text, "score": score})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


async def rag_context(query: str, top_k: int = 5) -> str:
    """检索 top-k 拼接为上下文文本（注入系统提示用）。"""
    hits = await retrieve(query, top_k)
    if not hits:
        return ""
    parts = []
    for h in hits:
        parts.append(f"[{h['section'] or h['path']}]\n{h['text']}")
    return "\n\n".join(parts)
