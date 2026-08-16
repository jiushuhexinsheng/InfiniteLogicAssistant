# -*- coding: utf-8 -*-
"""RAG 检索 — BM25 打分（纯 Python，无外部依赖）

优先读取索引期预计算的 chunk_terms（只加载分词结果，不加载全文，避免每次查询
全量重分词）；旧索引（无 chunk_terms 表）自动回退到读取全文现场分词。
"""
import math
import sqlite3

from core import rag as rag_mod
from core.rag.tokenize import tokenize

# BM25 超参
_K1 = 1.5
_B = 0.75


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


def _rank(query: list[str], docs: list[list[str]]) -> list[tuple[int, float]]:
    """对 doc token 列表做 BM25 打分，返回按得分降序的 (doc_index, score)。"""
    df: dict[str, int] = {}
    for dt in docs:
        for t in set(dt):
            df[t] = df.get(t, 0) + 1
    n = len(docs)
    idf = {t: math.log(1 + (n - freq + 0.5) / (freq + 0.5)) for t, freq in df.items()}
    doc_lens = [len(dt) for dt in docs]
    avgdl = sum(doc_lens) / n if n else 0.0
    scored = []
    for i, dt in enumerate(docs):
        score = _bm25_score(query, dt, idf, doc_lens[i], avgdl)
        if score > 0:
            scored.append((i, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


async def retrieve(query: str, top_k: int = 5) -> list[dict]:
    """BM25 检索，返回 top-k 块（[{path, section, text, score}]）。"""
    q_tokens = tokenize(query)
    if not q_tokens:
        return []
    with sqlite3.connect(str(rag_mod.INDEX_DB)) as conn:
        # 快路径：索引期预计算的 terms（只读分词结果，命中后再取文本）
        has_terms = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='chunk_terms'"
        ).fetchone()
        if has_terms:
            rows = conn.execute("SELECT chunk_id, terms FROM chunk_terms").fetchall()
            if rows:
                docs: list[tuple[int, list[str]]] = []
                for chunk_id, terms in rows:
                    docs.append((int(chunk_id), str(terms).split()))
                ranked = _rank(q_tokens, [d for _, d in docs])
                top = ranked[:top_k]
                if top:
                    ids = [docs[i][0] for i, _ in top]
                    placeholders = ",".join("?" * len(ids))
                    text_rows = conn.execute(
                        f"SELECT id, path, section, text FROM chunks WHERE id IN ({placeholders})",
                        ids,
                    ).fetchall()
                    text_map = {int(r[0]): (str(r[1]), str(r[2]), str(r[3])) for r in text_rows}
                    out = []
                    for i, score in top:
                        cid = docs[i][0]
                        path, section, text = text_map[cid]
                        out.append({"path": path, "section": section, "text": text, "score": round(score, 4)})
                    return out
            return []
        # 旧索引（无 chunk_terms 表）→ 全量读文本现场分词（向后兼容）
        has_chunks = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='chunks'"
        ).fetchone()
        if not has_chunks:
            return []  # 索引尚未构建（空库），视为无结果
        rows = conn.execute("SELECT path, section, text FROM chunks").fetchall()
    if not rows:
        return []
    legacy_docs = [tokenize(text) for _, _, text in rows]
    ranked = _rank(q_tokens, legacy_docs)
    out = []
    for i, score in ranked[:top_k]:
        path, section, text = rows[i]
        out.append({"path": path, "section": section, "text": text, "score": round(score, 4)})
    return out


async def rag_context(query: str, top_k: int = 5) -> str:
    """检索 top-k 拼接为上下文文本（注入系统提示用）。"""
    hits = await retrieve(query, top_k)
    if not hits:
        return ""
    parts = []
    for h in hits:
        parts.append(f"[{h['section'] or h['path']}]\n{h['text']}")
    return "\n\n".join(parts)
