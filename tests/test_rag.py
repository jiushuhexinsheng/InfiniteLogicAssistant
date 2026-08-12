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
