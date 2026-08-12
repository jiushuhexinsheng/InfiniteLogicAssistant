# -*- coding: utf-8 -*-
import pytest

from core.memory.facts import FactStore


@pytest.fixture
def store(tmp_path):
    return FactStore(tmp_path / "facts.sqlite")


@pytest.mark.asyncio
async def test_upsert_get(store):
    await store.upsert("偏好", "默认用中文", "smoke")
    rows = await store.get("偏好")
    assert rows and rows[0]["content"] == "默认用中文"


@pytest.mark.asyncio
async def test_upsert_merge_same_topic(store):
    await store.upsert("偏好", "v1", "a")
    await store.upsert("偏好", "v2", "b")
    rows = await store.get("偏好")
    assert len(rows) == 1 and rows[0]["content"] == "v2"


@pytest.mark.asyncio
async def test_search_by_keyword(store):
    await store.upsert("天气偏好", "喜欢看济南天气")
    await store.upsert("其他", "无关内容")
    hits = await store.search(["济南"])
    assert len(hits) == 1 and hits[0]["topic"] == "天气偏好"


@pytest.mark.asyncio
async def test_all_and_delete(store):
    await store.upsert("a", "1")
    await store.upsert("b", "2")
    assert len(await store.all()) == 2
    await store.delete("a")
    assert len(await store.all()) == 1
