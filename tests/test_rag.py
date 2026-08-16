# -*- coding: utf-8 -*-
import pytest

from core import rag as rag_mod
from core.rag.indexer import index_sources
from core.rag.retriever import rag_context, retrieve


@pytest.mark.asyncio
async def test_index_and_retrieve(tmp_path, monkeypatch):
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
    monkeypatch.setattr(rag_mod, "INDEX_DB", tmp_path / "index.db")
    src = tmp_path / "a.md"
    src.write_text("## 系统\n\nPython 版本 3.14", encoding="utf-8")
    await index_sources([src])
    ctx = await rag_context("python 版本")
    assert "Python" in ctx


@pytest.mark.asyncio
async def test_retrieve_empty_db(tmp_path, monkeypatch):
    monkeypatch.setattr(rag_mod, "INDEX_DB", tmp_path / "empty.db")
    assert await retrieve("anything") == []


@pytest.mark.asyncio
async def test_index_sources_hermetic_index_db(tmp_path):
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
    from core.rag import maybe_rebuild_index
    import core.rag.retriever as retriever_mod
    src = tmp_path / "env.md"
    src.write_text("## 系统\n\nPython 3.14", encoding="utf-8")
    db = tmp_path / "index.db"
    await maybe_rebuild_index([src], index_db=db)
    assert db.exists()
    monkeypatch.setattr(retriever_mod, "INDEX_DB", db)
    hits = await retrieve("python")
    assert hits and any("Python" in h["text"] for h in hits)


@pytest.mark.asyncio
async def test_maybe_rebuild_when_stale(tmp_path, monkeypatch):
    import os
    import time
    from core.rag import maybe_rebuild_index
    import core.rag.retriever as retriever_mod
    src = tmp_path / "env.md"
    src.write_text("## 系统\n\nPython 3.14", encoding="utf-8")
    db = tmp_path / "index.db"
    await maybe_rebuild_index([src], index_db=db)
    src.write_text("## 系统\n\nPython 3.15 更新了", encoding="utf-8")
    os.utime(src, (time.time() + 2, time.time() + 2))
    await maybe_rebuild_index([src], index_db=db)
    monkeypatch.setattr(retriever_mod, "INDEX_DB", db)
    hits = await retrieve("3.15")
    assert hits and any("3.15" in h["text"] for h in hits)


@pytest.mark.asyncio
async def test_maybe_rebuild_skips_fresh(tmp_path):
    from core.rag import maybe_rebuild_index
    src = tmp_path / "env.md"
    src.write_text("## 系统\n\nPython 3.14", encoding="utf-8")
    db = tmp_path / "index.db"
    await maybe_rebuild_index([src], index_db=db)
    before = db.stat().st_mtime_ns
    await maybe_rebuild_index([src], index_db=db)  # 源未变 → 不应重建
    assert db.stat().st_mtime_ns == before
