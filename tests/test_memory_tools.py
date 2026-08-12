# -*- coding: utf-8 -*-
import pytest

from core.memory.context import _facts_store
from core.memory.facts import FactStore
from core.tools import TOOLS


@pytest.mark.asyncio
async def test_memory_put_get(tmp_path, monkeypatch):
    monkeypatch.setattr("core.memory.context._facts_store", FactStore(tmp_path / "f.sqlite"))
    await TOOLS.acall("memory_put", {"topic": "偏好", "content": "默认用中文"})
    out = await TOOLS.acall("memory_get", {"topic": "偏好"})
    assert "默认用中文" in out


@pytest.mark.asyncio
async def test_memory_get_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("core.memory.context._facts_store", FactStore(tmp_path / "f.sqlite"))
    out = await TOOLS.acall("memory_get", {"topic": "不存在"})
    assert "无相关记忆" in out
