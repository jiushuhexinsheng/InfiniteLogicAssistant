# -*- coding: utf-8 -*-
import pytest

from core import rag as rag_mod
from core.memory.context import build_context
from core.memory.facts import FactStore
from core.rag.indexer import index_sources


@pytest.mark.asyncio
async def test_build_context_merges_rag_and_facts(tmp_path, monkeypatch):
    monkeypatch.setattr(rag_mod, "INDEX_DB", tmp_path / "index.db")
    src = tmp_path / "env.md"
    src.write_text("## 系统\n\nPython 3.14", encoding="utf-8")
    await index_sources([src])
    store = FactStore(tmp_path / "facts.sqlite")
    await store.upsert("python偏好", "用户喜欢用 python 开发")

    ctx = await build_context("python", store=store)
    assert "Python" in ctx          # RAG 片段
    assert "python偏好" in ctx      # 长期事实


@pytest.mark.asyncio
async def test_build_context_facts_only(tmp_path, monkeypatch):
    monkeypatch.setattr(rag_mod, "INDEX_DB", tmp_path / "empty.db")
    store = FactStore(tmp_path / "facts.sqlite")
    await store.upsert("偏好", "默认用中文")
    ctx = await build_context("偏好", store=store)
    assert "默认用中文" in ctx


@pytest.mark.asyncio
async def test_build_context_empty_when_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(rag_mod, "INDEX_DB", tmp_path / "empty.db")
    store = FactStore(tmp_path / "facts.sqlite")
    assert await build_context("完全无关词", store=store) == ""
