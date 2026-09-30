# -*- coding: utf-8 -*-
"""测试事实库的增改查、关键词搜索、FTS 同步与删除功能。
Tests the fact store: upsert, query, keyword search, FTS sync, and deletion.

含 ADD-only 协调语义（docs/designs/04 §3.1）：等价复述只刷 ts、冲突失效旧行、
读口只回现行有效行、新近度加权与注入条数上限。
"""
import pytest

from core.memory.facts import FactStore


@pytest.fixture
def store(tmp_path):
    return FactStore(tmp_path / "facts.sqlite")


@pytest.mark.asyncio
async def test_upsert_get(store):
    """测试事实写入后可按主题读取。Tests that a fact can be read back by topic after upsert."""
    await store.upsert("偏好", "默认用中文", "smoke")
    rows = await store.get("偏好")
    assert rows and rows[0]["content"] == "默认用中文"


@pytest.mark.asyncio
async def test_upsert_merge_same_topic(store):
    """测试同一主题重复写入会合并覆盖旧内容。Tests that re-upserting the same topic merges and overwrites the old content."""
    await store.upsert("偏好", "v1", "a")
    await store.upsert("偏好", "v2", "b")
    rows = await store.get("偏好")
    assert len(rows) == 1 and rows[0]["content"] == "v2"


@pytest.mark.asyncio
async def test_search_by_keyword(store):
    """测试按关键词能命中匹配的事实。Tests that keyword search hits the matching fact."""
    await store.upsert("天气偏好", "喜欢看济南天气")
    await store.upsert("其他", "无关内容")
    hits = await store.search(["济南"])
    assert len(hits) == 1 and hits[0]["topic"] == "天气偏好"


@pytest.mark.asyncio
async def test_fts_search_ranked(store):
    """测试全文检索按命中次数进行排名。Tests that full-text search ranks results by hit count."""
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
    """测试更新与删除事实时全文索引同步维护。Tests that the FTS index stays in sync on fact update and delete."""
    await store.upsert("k", "旧关键词天气预报")
    assert await store.search(["天气预报"])
    await store.upsert("k", "新内容卫星云图")
    assert not await store.search(["天气预报"])   # 更新后旧内容应从 FTS 移除
    assert await store.search(["卫星云图"])
    await store.delete("k")
    assert not await store.search(["卫星云图"])    # 删除后 FTS 同步移除


@pytest.mark.asyncio
async def test_all_and_delete(store):
    """测试列出全部事实与删除指定事实。Tests listing all facts and deleting a specific fact."""
    await store.upsert("a", "1")
    await store.upsert("b", "2")
    assert len(await store.all()) == 2
    await store.delete("a")
    assert len(await store.all()) == 1


# ─── ADD-only 协调语义（docs/designs/04 §3.1）───


@pytest.mark.asyncio
async def test_equivalent_restatement_refreshes_ts_keeps_source(store):
    """等价复述只刷新 ts，来源不被后来者偷走（voice 复述 task 事实不改 source）。"""
    await store.upsert("偏好", "默认用中文", "task:1")
    with store._conn() as conn:
        conn.execute("UPDATE facts SET ts='2020-01-01T00:00:00' WHERE topic='偏好'")
    await store.upsert("偏好", "默认用中文", "voice")   # 等价复述。Equivalent restatement.
    rows = await store.get("偏好")
    assert len(rows) == 1
    assert rows[0]["ts"] != "2020-01-01T00:00:00"       # ts 已刷新。ts refreshed.
    assert rows[0]["source"] == "task:1"                # 来源保留。Source preserved.


@pytest.mark.asyncio
async def test_conflict_retires_old_row_history_kept(store):
    """冲突 → 旧行失效（历史可查）而非删除；读口与 all() 只回现行；失效行不进检索。"""
    await store.upsert("偏好", "喜欢咖啡", "task:1")
    await store.upsert("偏好", "完全改掉了，现在喜欢喝茶这一套", "voice", path="偏好")

    active = await store.get("偏好")
    assert len(active) == 1
    assert active[0]["content"].startswith("完全改掉")
    assert active[0]["source"] == "voice"
    assert active[0]["path"] == "偏好"

    hist = await store.history("偏好")
    assert len(hist) == 2
    retired = [h for h in hist if h.get("valid_until")]
    assert len(retired) == 1 and retired[0]["content"] == "喜欢咖啡"

    assert len(await store.all()) == 1                   # 只回现行。Active only.
    assert not await store.search(["喜欢咖啡"])           # 失效行不检索。Retired rows not searchable.


@pytest.mark.asyncio
async def test_search_limit(store):
    """limit 控制注入条数（注入预算的条数闸）。limit caps the injected row count."""
    for i in range(7):
        await store.upsert(f"主题{i}", f"检索关键词内容{i}")
    hits = await store.search(["检索关键词"], limit=3)
    assert len(hits) == 3


@pytest.mark.asyncio
async def test_recency_weight_promotes_fresh(store, monkeypatch):
    """新近度加权：bm25 平分时更新的事实排前；权重 0 退化纯 bm25（召回不变）。"""
    from core import config
    await store.upsert("事实甲", "关键词相同内容", "s")   # 保持最新。Stays fresh.
    await store.upsert("事实乙", "关键词相同内容", "s")
    with store._conn() as conn:
        conn.execute("UPDATE facts SET ts='2020-01-01T00:00:00' WHERE topic='事实乙'")

    monkeypatch.setattr(config.settings.memory, "recency_weight", 0.5)
    hits = await store.search(["关键词"])
    assert [h["topic"] for h in hits][:2] == ["事实甲", "事实乙"], "新事实应被加权到前"

    monkeypatch.setattr(config.settings.memory, "recency_weight", 0)
    hits0 = await store.search(["关键词"])
    assert {h["topic"] for h in hits0} == {"事实甲", "事实乙"}, "关权重不改变召回"
