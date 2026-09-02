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
