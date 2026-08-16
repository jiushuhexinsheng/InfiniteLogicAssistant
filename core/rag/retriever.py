# -*- coding: utf-8 -*-
"""RAG 检索 — BM25 打分（纯 Python，无外部依赖）

分词：ASCII 词（≥2 字符）按整词；中文按字符二元组（无外部依赖的中文近似分词）。
"""
import math
import re
import sqlite3

from core.rag import INDEX_DB

_TOKEN_RE = re.compile(r"[a-z0-9_]+|[一-鿿]+")

# BM25 超参
_K1 = 1.5
_B = 0.75


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for m in _TOKEN_RE.findall(text.lower()):
        if not m:
            continue
        if m[0].isascii():
            if len(m) >= 2:
                tokens.append(m)
        else:
            # 中文：按字符二元组切分，允许子串匹配
            if len(m) >= 2:
                tokens.extend(m[i:i + 2] for i in range(len(m) - 1))
    return tokens


def _bm25_score(query: list[str], doc: list[str], idf: dict[str, float], doc_len: int, avgdl: float) -> float:
    """单文档 BM25 得分。"""
    tf: dict[str, int] = {}
    for t in doc:
        tf[t] = tf.get(t, 0) + 1
    score = 0.0
    for t in query:
        if t not in idf or t not in tf:
            continue
        f = tf[t]
        denom = f + _K1 * (1 - _B + _B * doc_len / avgdl) if avgdl > 0 else f + _K1
        score += idf[t] * f * (_K1 + 1) / denom
    return score


async def retrieve(query: str, top_k: int = 5) -> list[dict]:
    """BM25 检索，返回 top-k 块（[{path, section, text, score}]）。"""
    q_tokens = _tokenize(query)
    if not q_tokens:
        return []
    with sqlite3.connect(str(INDEX_DB)) as conn:
        rows = conn.execute("SELECT path, section, text FROM chunks").fetchall()
    if not rows:
        return []
    doc_tokens = [_tokenize(text) for _, _, text in rows]
    # 文档频率 → idf
    df: dict[str, int] = {}
    for dt in doc_tokens:
        for t in set(dt):
            df[t] = df.get(t, 0) + 1
    n = len(rows)
    idf = {t: math.log(1 + (n - freq + 0.5) / (freq + 0.5)) for t, freq in df.items()}
    doc_lens = [len(dt) for dt in doc_tokens]
    avgdl = sum(doc_lens) / n if n else 0.0
    scored = []
    for i, (path, section, text) in enumerate(rows):
        score = _bm25_score(q_tokens, doc_tokens[i], idf, doc_lens[i], avgdl)
        if score > 0:
            scored.append({"path": path, "section": section, "text": text, "score": round(score, 4)})
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
