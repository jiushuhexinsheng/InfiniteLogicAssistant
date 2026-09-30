# -*- coding: utf-8 -*-
"""RAG 索引与检索（core.rag）的测试。
Tests for RAG indexing and retrieval (core.rag).
"""
import pytest

from core import rag as rag_mod
from core.rag.indexer import index_sources
from core.rag.retriever import rag_context, retrieve


@pytest.mark.asyncio
async def test_index_and_retrieve(tmp_path, monkeypatch):
    """测试索引后可按关键词检索命中内容。Tests retrieval hitting indexed content by keyword."""
    monkeypatch.setattr(rag_mod, "INDEX_DB", tmp_path / "index.db")
    src = tmp_path / "env.md"
    src.write_text(
        "# 环境\n\n## 系统\n\n- Python：3.14.7\n\n## 硬件\n\n- 磁盘：总 236 GB\n",
        encoding="utf-8",
    )
    await index_sources([src])
    hits = await retrieve("python")
    assert hits and any("Python" in h["text"] for h in hits)
    hits2 = await retrieve("磁盘")
    assert hits2 and any("磁盘" in h["text"] for h in hits2)


@pytest.mark.asyncio
async def test_rag_context_joins_topk(tmp_path, monkeypatch):
    """测试 rag_context 拼接 top-k 片段生成上下文。Tests rag_context joining top-k chunks into a context."""
    monkeypatch.setattr(rag_mod, "INDEX_DB", tmp_path / "index.db")
    src = tmp_path / "a.md"
    src.write_text("## 系统\n\nPython 版本 3.14", encoding="utf-8")
    await index_sources([src])
    ctx = await rag_context("python 版本")
    assert "Python" in ctx


@pytest.mark.asyncio
async def test_retrieve_empty_db(tmp_path, monkeypatch):
    """测试空数据库检索返回空列表。Tests retrieval on an empty database returning an empty list."""
    monkeypatch.setattr(rag_mod, "INDEX_DB", tmp_path / "empty.db")
    assert await retrieve("anything") == []


@pytest.mark.asyncio
async def test_index_sources_hermetic_index_db(tmp_path):
    """测试 index_sources 使用指定 index_db 建库（隔离测试）。Tests index_sources building a hermetic index database."""
    src = tmp_path / "src.md"
    src.write_text("## 主题\n\n内容", encoding="utf-8")
    db = tmp_path / "hermetic.db"
    await index_sources([src], index_db=db)
    import sqlite3
    conn = sqlite3.connect(str(db))
    try:
        n = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    finally:
        conn.close()
    assert n >= 1


@pytest.mark.asyncio
async def test_maybe_rebuild_missing_db(tmp_path, monkeypatch):
    """测试索引缺失时 maybe_rebuild_index 自动重建。Tests maybe_rebuild_index rebuilding when the index is missing."""
    from core.rag import maybe_rebuild_index
    import core.rag as rag_mod
    src = tmp_path / "env.md"
    src.write_text("## 系统\n\nPython 3.14", encoding="utf-8")
    db = tmp_path / "index.db"
    await maybe_rebuild_index([src], index_db=db)
    assert db.exists()
    monkeypatch.setattr(rag_mod, "INDEX_DB", db)
    hits = await retrieve("python")
    assert hits and any("Python" in h["text"] for h in hits)


@pytest.mark.asyncio
async def test_maybe_rebuild_when_stale(tmp_path, monkeypatch):
    """测试源文件变更后 maybe_rebuild_index 重建索引。Tests maybe_rebuild_index rebuilding after source files change."""
    import os
    import time
    from core.rag import maybe_rebuild_index
    import core.rag as rag_mod
    src = tmp_path / "env.md"
    src.write_text("## 系统\n\nPython 3.14", encoding="utf-8")
    db = tmp_path / "index.db"
    await maybe_rebuild_index([src], index_db=db)
    src.write_text("## 系统\n\nPython 3.15 更新了", encoding="utf-8")
    os.utime(src, (time.time() + 2, time.time() + 2))
    await maybe_rebuild_index([src], index_db=db)
    monkeypatch.setattr(rag_mod, "INDEX_DB", db)
    hits = await retrieve("3.15")
    assert hits and any("3.15" in h["text"] for h in hits)


@pytest.mark.asyncio
async def test_index_stores_terms(tmp_path):
    """索引期应预计算并存储分词结果（避免检索时全量重分词）。
    The indexer should precompute and store tokenization results to avoid re-tokenizing during retrieval.
    """
    src = tmp_path / "src.md"
    src.write_text("## 主题\n\nPython 版本 3.14 与 磁盘 检查", encoding="utf-8")
    db = tmp_path / "index.db"
    await index_sources([src], index_db=db)
    import sqlite3
    conn = sqlite3.connect(str(db))
    try:
        n = conn.execute("SELECT COUNT(*) FROM chunk_terms").fetchone()[0]
        terms = conn.execute("SELECT terms FROM chunk_terms LIMIT 1").fetchone()[0]
    finally:
        conn.close()
    assert n >= 1
    assert "python" in terms  # 英文整词
    assert "磁盘" in terms    # 中文二元组


@pytest.mark.asyncio
async def test_retrieve_legacy_db_without_terms(tmp_path, monkeypatch):
    """旧索引（无 chunk_terms 表）仍可检索（向后兼容）。
    Legacy indexes without a chunk_terms table remain searchable (backward compatibility).
    """
    import sqlite3
    import core.rag as rag_mod
    db = tmp_path / "legacy.db"
    monkeypatch.setattr(rag_mod, "INDEX_DB", db)
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("CREATE TABLE chunks (id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT, section TEXT, text TEXT)")
        conn.execute("INSERT INTO chunks (path, section, text) VALUES (?,?,?)", ("env.md", "系统", "Python 版本 3.14"))
        conn.commit()
    finally:
        conn.close()
    hits = await retrieve("python")
    assert hits and "Python" in hits[0]["text"]


@pytest.mark.asyncio
async def test_bm25_ranks_relevant_higher(tmp_path, monkeypatch):
    """测试 BM25 将命中更多查询词的片段排在前面。Tests BM25 ranking chunks matching more query terms first."""
    import core.rag as rag_mod
    db = tmp_path / "index.db"
    monkeypatch.setattr(rag_mod, "INDEX_DB", db)
    src = tmp_path / "docs.md"
    src.write_text(
        "# 文档\n\n## 相关段\n\nPython 版本 3.14 与 pip 包管理\n\n## 无关段\n\n天气不错适合散步\n",
        encoding="utf-8",
    )
    await index_sources([src], index_db=db)
    hits = await retrieve("python 包管理")
    assert hits and "Python" in hits[0]["text"]  # 命中多个查询词的段排最前


@pytest.mark.asyncio
async def test_maybe_rebuild_skips_fresh(tmp_path):
    """测试源文件未变化时 maybe_rebuild_index 跳过重建。Tests maybe_rebuild_index skipping rebuild when sources are unchanged."""
    from core.rag import maybe_rebuild_index
    src = tmp_path / "env.md"
    src.write_text("## 系统\n\nPython 3.14", encoding="utf-8")
    db = tmp_path / "index.db"
    await maybe_rebuild_index([src], index_db=db)
    before = db.stat().st_mtime_ns
    await maybe_rebuild_index([src], index_db=db)  # 源未变 → 不应重建
    assert db.stat().st_mtime_ns == before


# ─── 编号注入与 LLM 精排（docs/designs/05）───


@pytest.mark.asyncio
async def test_rag_context_numbered_format(tmp_path, monkeypatch):
    """注入文本带编号 [n] 与 path（LLM 引用标注的依据）。Injection text is numbered
    [n] with the path (the basis for LLM citations)."""
    monkeypatch.setattr(rag_mod, "INDEX_DB", tmp_path / "index.db")
    src = tmp_path / "a.md"
    src.write_text("## 系统\n\nPython 版本 3.14", encoding="utf-8")
    await index_sources([src])
    ctx = await rag_context("python 版本")
    assert "[1]" in ctx and "a.md" in ctx


@pytest.mark.asyncio
async def test_rerank_reorders_by_llm_score(monkeypatch):
    """rerank=llm：按模型分数重排并截断 top_k。Rerank reorders by model score and cuts to top_k."""
    import json as _json
    from core.rag import retriever as rv

    hits = [
        {"path": "a.md", "section": "A", "text": "aaa", "score": 3.0},
        {"path": "b.md", "section": "B", "text": "bbb", "score": 2.0},
        {"path": "c.md", "section": "C", "text": "ccc", "score": 1.0},
    ]

    class _FakeLLM:
        def retry_stream_chat(self, messages, tools=None, temperature=None):
            async def gen():
                yield {"type": "done", "message": {"tool_calls": [{"function": {
                    "arguments": _json.dumps({"scores": [
                        {"n": 1, "score": 2}, {"n": 2, "score": 9}, {"n": 3, "score": 6},
                    ]})}}]}}
            return gen()

    monkeypatch.setattr("core.llm.client.get_llm_client", lambda: _FakeLLM())
    out = await rv.rerank("q", hits, top_k=2)
    assert [h["path"] for h in out] == ["b.md", "c.md"]


@pytest.mark.asyncio
async def test_rerank_failure_falls_back_to_bm25(monkeypatch):
    """rerank 任何失败 → 静默回退 BM25 序（rerank 坏了不得拖垮整个回合）。
    Any rerank failure silently falls back to the BM25 order (a broken rerank must
    not take the turn down)."""
    from core.rag import retriever as rv

    hits = [
        {"path": "a.md", "section": "A", "text": "aaa", "score": 3.0},
        {"path": "b.md", "section": "B", "text": "bbb", "score": 2.0},
        {"path": "c.md", "section": "C", "text": "ccc", "score": 1.0},
    ]

    class _Boom:
        def retry_stream_chat(self, messages, tools=None, temperature=None):
            raise RuntimeError("LLM down")
            yield  # pragma: no cover —— 让它是生成器。Makes it a generator.

    monkeypatch.setattr("core.llm.client.get_llm_client", lambda: _Boom())
    out = await rv.rerank("q", hits, top_k=2)
    assert [h["path"] for h in out] == ["a.md", "b.md"]
