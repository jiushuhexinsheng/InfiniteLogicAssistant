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
async def test_fts_search_ranked(store):
    await store.upsert("a", "用户每天看天气预报")
    await store.upsert("b", "天气预报 天气预报 重要")
    await store.upsert("c", "无关内容")
    hits = await store.search(["天气预报"])
    topics = [h["topic"] for h in hits]
    assert "a" in topics and "b" in topics and "c" not in topics
    # b 命中次数更多，bm25 排名更优 → 排前
    assert topics.index("b") < topics.index("a")


@pytest.mark.asyncio
async def test_fts_sync_on_update_delete(store):
    await store.upsert("k", "旧关键词天气预报")
    assert await store.search(["天气预报"])
    await store.upsert("k", "新内容卫星云图")
    assert not await store.search(["天气预报"])   # 更新后旧内容应从 FTS 移除
    assert await store.search(["卫星云图"])
    await store.delete("k")
    assert not await store.search(["卫星云图"])    # 删除后 FTS 同步移除


@pytest.mark.asyncio
async def test_all_and_delete(store):
    await store.upsert("a", "1")
    await store.upsert("b", "2")
    assert len(await store.all()) == 2
    await store.delete("a")
    assert len(await store.all()) == 1
