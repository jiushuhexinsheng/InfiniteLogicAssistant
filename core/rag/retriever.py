# -*- coding: utf-8 -*-
"""RAG 检索 — BM25 打分（纯 Python，无外部依赖）
RAG retrieval — BM25 scoring (pure Python, no external dependencies).

优先读取索引期预计算的 chunk_terms（只加载分词结果，不加载全文，避免每次查询
全量重分词）；旧索引（无 chunk_terms 表）自动回退到读取全文现场分词。
Prefers the precomputed chunk_terms from indexing time (loading only token results, not full text, to avoid full re-tokenization on every query); older indexes (without a chunk_terms table) automatically fall back to reading the full text and tokenizing on the fly.
"""
import json
import math
import sqlite3

from core import rag as rag_mod
from core.rag.tokenize import tokenize

# BM25 超参
_K1 = 1.5
_B = 0.75


def _bm25_score(query: list[str], doc: list[str], idf: dict[str, float], doc_len: int, avgdl: float) -> float:
    """单文档 BM25 得分。BM25 score for a single document."""
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
    """对 doc token 列表做 BM25 打分，返回按得分降序的 (doc_index, score)。
    Ranks doc token lists with BM25 scoring and returns (doc_index, score) pairs sorted by score in descending order."""
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
    """BM25 检索，返回 top-k 块（[{path, section, text, score}]）。
    BM25 retrieval, returning the top-k chunks ([{path, section, text, score}])."""
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


def format_hits(hits: list[dict]) -> str:
    """命中 → 编号注入文本（docs/designs/05 §3.1：`[n] 标题 (path)` 供 LLM 标注引用）。

    Hits → numbered injection text (docs/designs/05 §3.1: `[n] title (path)` so the
    LLM can cite sources).

    Args:
        hits: 检索命中（含 path/section/text）。Retrieval hits (with path/section/text).

    Returns:
        编号拼接的上下文文本（空命中为空串）。Numbered context text (empty for no hits).
    """
    if not hits:
        return ""
    parts = []
    for i, h in enumerate(hits):
        parts.append(f"[{i + 1}] {h['section'] or h['path']} ({h['path']})\n{h['text']}")
    return "\n\n".join(parts)


# rerank 打分工具：闭集输出 [{n, score}]，n 为候选编号（1 起），score 0-10。
# Rerank scoring tool: closed-set output [{n, score}] with 1-based candidate numbers
# and a 0-10 score.
_RERANK_TOOL = {
    "type": "function",
    "function": {
        "name": "score_sources",
        "description": "按与查询的相关度给候选资料片段打分（0-10，越高越相关）",
        "parameters": {
            "type": "object",
            "properties": {
                "scores": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "n": {"type": "integer"},
                            "score": {"type": "number"},
                        },
                        "required": ["n", "score"],
                    },
                },
            },
            "required": ["scores"],
        },
    },
}


async def rerank(query: str, hits: list[dict], top_k: int) -> list[dict]:
    """LLM 精排（docs/designs/05 §3.3，配置 `rag.rerank='llm'` 时启用）。

    单次调用对候选闭集打分重排；**任何失败（超时/坏 JSON/无工具调用）静默回退
    BM25 序**并记审计 `rag-rerank-fallback`。候选 ≤ top_k 时调用方本就不该进来，
    这里再兜一层直接截断返回。

    LLM rerank (docs/designs/05 §3.3, enabled by `rag.rerank='llm'`): one call
    scores the candidate set and reorders it; **any failure (timeout / bad JSON /
    missing tool call) silently falls back to the BM25 order** with an audit line
    `rag-rerank-fallback`. Fewer candidates than top_k short-circuits to a slice.

    Args:
        query: 用户查询。The user query.
        hits: BM25 粗排候选。BM25 candidates.
        top_k: 精排后保留条数。Rows to keep after reranking.

    Returns:
        重排后的命中列表。Reordered hits.
    """
    if len(hits) <= top_k:
        return hits[:top_k]
    try:
        from core.llm.client import get_llm_client
        from core.logger import audit

        lines = [f"[{i + 1}] {h['section'] or h['path']}\n{h['text'][:300]}"
                 for i, h in enumerate(hits)]
        messages = [
            {"role": "system", "content": "你在为检索结果精排：给每个候选片段打 0-10 分"
                                          "（与查询的相关度）。为每个候选都给分，用 score_sources 返回。"},
            {"role": "user", "content": f"查询：{query}\n\n候选：\n" + "\n\n".join(lines)},
        ]
        async for evt in get_llm_client().retry_stream_chat(
            messages, tools=[_RERANK_TOOL], temperature=0,
        ):
            if evt["type"] == "done":
                msg = evt["message"] or {}
                tc = (msg.get("tool_calls") or [{}])[0]
                raw = tc.get("function", {}).get("arguments") or "{}"
                data = json.loads(raw) if isinstance(raw, str) else raw
                scores = {int(s["n"]): float(s["score"]) for s in data.get("scores") or []}
                if not scores:
                    raise ValueError("rerank 无分数")
                ranked = sorted(
                    enumerate(hits),
                    key=lambda iv: (scores.get(iv[0] + 1, -1.0), -iv[0]),
                    reverse=True,
                )
                out = [h for _, h in ranked][:top_k]
                audit(f"rag-rerank n={len(hits)} top={len(out)}")
                return out
        raise ValueError("rerank 无工具调用")
    except Exception as e:
        from core.logger import audit, logger
        logger.warning("rag rerank 失败，回退 BM25 序: {}", e)
        audit("rag-rerank-fallback")
        return hits[:top_k]


async def rag_context(query: str, top_k: int = 5) -> str:
    """检索 top-k 拼接为上下文文本（注入系统提示用；编号格式见 format_hits）。
    Retrieves the top-k hits and joins them into a numbered context text (for the
    system prompt; see format_hits for the numbering format)."""
    hits = await retrieve(query, top_k)
    return format_hits(hits)
