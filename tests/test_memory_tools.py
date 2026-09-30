# -*- coding: utf-8 -*-
"""记忆工具（memory_put/memory_get）的测试。
Tests for the memory tools (memory_put/memory_get).
"""
import pytest

from core.memory.facts import FactStore
from core.tools import TOOLS


@pytest.mark.asyncio
async def test_memory_put_get(tmp_path, monkeypatch):
    """测试记忆的写入与读取。Tests writing and reading a memory."""
    monkeypatch.setattr("core.tools.memory_tools.get_facts_store", lambda: FactStore(tmp_path / "f.sqlite"))
    await TOOLS.acall("memory_put", {"topic": "偏好", "content": "默认用中文"})
    out = await TOOLS.acall("memory_get", {"topic": "偏好"})
    assert "默认用中文" in out


@pytest.mark.asyncio
async def test_memory_get_missing(tmp_path, monkeypatch):
    """测试查询不存在的记忆时的兜底提示。Tests the fallback message for a missing memory."""
    monkeypatch.setattr("core.tools.memory_tools.get_facts_store", lambda: FactStore(tmp_path / "f.sqlite"))
    out = await TOOLS.acall("memory_get", {"topic": "不存在"})
    assert "无相关记忆" in out


@pytest.mark.asyncio
async def test_memory_search_and_delete(tmp_path, monkeypatch):
    """新增的记忆工具（docs/designs/04 §3.4）：检索带路径/时间，删除后读不到。"""
    monkeypatch.setattr("core.tools.memory_tools.get_facts_store", lambda: FactStore(tmp_path / "f.sqlite"))
    await TOOLS.acall("memory_put", {"topic": "咖啡偏好", "content": "喜欢 espresso", "path": "偏好"})

    out = await TOOLS.acall("memory_search", {"query": "espresso"})
    assert "espresso" in out and "偏好/" in out, "检索结果应带 path 前缀"

    out = await TOOLS.acall("memory_search", {"query": "espresso", "path": "习惯"})
    assert "无相关记忆" in out, "path 过滤应生效"

    out = await TOOLS.acall("memory_delete", {"topic": "咖啡偏好"})
    assert "已删除" in out
    assert "无相关记忆" in await TOOLS.acall("memory_get", {"topic": "咖啡偏好"})

    out = await TOOLS.acall("memory_delete", {"topic": "不存在"})
    assert "没有名为" in out
