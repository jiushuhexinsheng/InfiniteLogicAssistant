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
