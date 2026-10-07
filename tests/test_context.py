# -*- coding: utf-8 -*-
"""该模块测试 core.memory.context.build_context 合并 RAG 检索片段与长期事实来构建上下文的行为。
Tests how core.memory.context.build_context merges RAG snippets with long-term facts to build context.
"""
import pytest

from core import rag as rag_mod
from core.memory.context import build_context
from core.memory.facts import FactStore
from core.rag.indexer import index_sources


@pytest.mark.asyncio
async def test_build_context_merges_rag_and_facts(tmp_path, monkeypatch):
    """验证上下文同时包含 RAG 片段与长期事实。Verifies the context contains both RAG snippets and long-term facts."""
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
    """验证无 RAG 命中时上下文仅包含长期事实。Verifies the context contains only long-term facts when no RAG snippets match."""
    monkeypatch.setattr(rag_mod, "INDEX_DB", tmp_path / "empty.db")
    store = FactStore(tmp_path / "facts.sqlite")
    await store.upsert("偏好", "默认用中文")
    ctx = await build_context("偏好", store=store)
    assert "默认用中文" in ctx


@pytest.mark.asyncio
async def test_build_context_empty_when_nothing(tmp_path, monkeypatch):
    """验证无任何匹配时上下文为空字符串。Verifies the context is an empty string when nothing matches."""
    monkeypatch.setattr(rag_mod, "INDEX_DB", tmp_path / "empty.db")
    store = FactStore(tmp_path / "facts.sqlite")
    assert await build_context("完全无关词", store=store) == ""


@pytest.mark.asyncio
async def test_build_context_budget_topk_and_date(tmp_path, monkeypatch):
    """注入有界（docs/designs/04 §3.2）：top-k 条数闸 + 字符预算 + 每行带日期。"""
    from core import config
    monkeypatch.setattr(rag_mod, "INDEX_DB", tmp_path / "empty.db")
    monkeypatch.setattr(config.settings.memory, "inject_top_k", 2)
    monkeypatch.setattr(config.settings.memory, "inject_max_chars", 120)
    store = FactStore(tmp_path / "facts.sqlite")
    for i in range(5):
        await store.upsert(f"主题{i}", f"注入预算内容{i} " + "填充内容" * 15)

    ctx = await build_context("注入预算", store=store)
    fact_lines = [ln for ln in ctx.splitlines() if ln.startswith("- ")]
    assert 1 <= len(fact_lines) <= 2, "条数受 inject_top_k 约束"
    # 日期标注（对齐 memory_get 的读口径）。Date stamp (aligned with memory_get).
    assert any(len(ln) >= 10 and "（20" in ln for ln in fact_lines), "每行应带（YYYY-MM-DD）"

    # 预算收紧到只放得下第一条：仍至少注入 1 条（宁缺勿滥）。
    monkeypatch.setattr(config.settings.memory, "inject_max_chars", 10)
    ctx2 = await build_context("注入预算", store=store)
    lines2 = [ln for ln in ctx2.splitlines() if ln.startswith("- ")]
    assert len(lines2) == 1


# ── RAG 结果缓存接线（P2-5：rerank=llm 每查都花钱，重复查询须命中缓存）──

@pytest.mark.asyncio
async def test_build_context_rag_hits_cache_on_repeat_query(tmp_path, monkeypatch):
    """同一查询第二次构建不再调 retrieve/rerank（LLM 精排费只花一次）。
    A repeated query skips retrieve/rerank (the LLM rerank charge happens once)."""
    from core import config
    from core.memory import context as ctx_mod
    from core.rag import retriever
    monkeypatch.setattr(rag_mod, "INDEX_DB", tmp_path / "index.db")
    src = tmp_path / "env.md"
    src.write_text("## 系统\n\nPython 3.14", encoding="utf-8")
    await index_sources([src])
    monkeypatch.setattr(config.settings.rag, "rerank", "none")

    calls = {"retrieve": 0, "rerank": 0}
    real_retrieve = retriever.retrieve
    async def spy_retrieve(q, top_k=5):
        calls["retrieve"] += 1
        return await real_retrieve(q, top_k)
    async def spy_rerank(q, hits, top_k):
        calls["rerank"] += 1
        return hits[:top_k]
    monkeypatch.setattr(retriever, "retrieve", spy_retrieve)
    monkeypatch.setattr(retriever, "rerank", spy_rerank)

    store = FactStore(tmp_path / "facts.sqlite")
    ctx1 = await ctx_mod.build_context("python", store=store)
    ctx2 = await ctx_mod.build_context("python", store=store)
    assert "Python" in ctx1 and ctx2 == ctx1
    assert calls["retrieve"] == 1, f"第二次该命中缓存，实测 retrieve 调了 {calls['retrieve']} 次"

    # 不同查询不受影响（各自建键）。A different query still retrieves.
    await ctx_mod.build_context("磁盘", store=store)
    assert calls["retrieve"] == 2


@pytest.mark.asyncio
async def test_build_context_rag_cache_with_llm_rerank(tmp_path, monkeypatch):
    """rerank=llm 档：第二次同查询连 rerank LLM 调用都省掉。
    With rerank='llm', the second identical query skips the rerank LLM call too."""
    from core import config
    from core.memory import context as ctx_mod
    from core.rag import retriever
    monkeypatch.setattr(rag_mod, "INDEX_DB", tmp_path / "index.db")
    src = tmp_path / "env.md"
    src.write_text("## 系统\n\nPython 3.14 与磁盘 236GB", encoding="utf-8")
    await index_sources([src])
    monkeypatch.setattr(config.settings.rag, "rerank", "llm")

    calls = {"rerank": 0}
    async def spy_rerank(q, hits, top_k):
        calls["rerank"] += 1
        return hits[:top_k]
    monkeypatch.setattr(retriever, "rerank", spy_rerank)

    store = FactStore(tmp_path / "facts.sqlite")
    await ctx_mod.build_context("python 磁盘", store=store)
    await ctx_mod.build_context("python 磁盘", store=store)
    assert calls["rerank"] == 1, f"第二次该命中缓存，实测 rerank 调了 {calls['rerank']} 次"


@pytest.mark.asyncio
async def test_index_rebuild_invalidates_cache(tmp_path, monkeypatch):
    """索引重建清空缓存——重建后的新增内容必须立刻可检索到。
    Index rebuild clears the cache — newly indexed content is immediately findable."""
    from core import config
    from core.memory import context as ctx_mod
    monkeypatch.setattr(rag_mod, "INDEX_DB", tmp_path / "index.db")
    src = tmp_path / "env.md"
    src.write_text("## 系统\n\nPython 3.14", encoding="utf-8")
    await index_sources([src])
    monkeypatch.setattr(config.settings.rag, "rerank", "none")
    store = FactStore(tmp_path / "facts.sqlite")

    assert "Python" in await ctx_mod.build_context("python", store=store)
    # 重建：加入新内容、删掉旧的。Rebuild with new content replacing the old.
    src.write_text("## 系统\n\nRust 工具链", encoding="utf-8")
    await index_sources([src])
    ctx = await ctx_mod.build_context("python", store=store)
    assert "Python" not in ctx, "重建后仍返回旧缓存 = 失效没接上"
