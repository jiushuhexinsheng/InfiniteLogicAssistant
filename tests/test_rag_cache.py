# -*- coding: utf-8 -*-
"""RAG 检索/精排结果缓存（core.rag.cache）——省掉重复查询的 BM25 重算与 rerank LLM 花费。
RAG retrieval/rerank result cache (core.rag.cache) — saves repeated BM25 recomputation
and rerank LLM spend."""
from core import config
from core.rag import cache as cache_mod


def test_miss_returns_none_then_hit_returns_value():
    """未命中 None（区别于命中空列表），命中回原值。Miss is None (distinct from a
    cached empty list); a hit returns the stored value."""
    assert cache_mod.get("k1") is None
    cache_mod.set("k1", [])
    assert cache_mod.get("k1") == []      # 空结果也缓存（索引未建时免重复全扫）
    cache_mod.set("k2", [{"path": "a"}])
    assert cache_mod.get("k2") == [{"path": "a"}]
    cache_mod.clear()


def test_ttl_expiry(monkeypatch):
    """TTL 到期自动失效。Entries expire after the TTL."""
    now = {"t": 1000.0}
    monkeypatch.setattr(cache_mod.time, "monotonic", lambda: now["t"])
    cache_mod.clear()
    cache_mod.set("k", ["v"])
    now["t"] += config.settings.rag.cache_ttl_s - 1
    assert cache_mod.get("k") == ["v"]    # 未到期仍在。Not yet expired.
    now["t"] += 1
    assert cache_mod.get("k") is None     # 到期即失效。Expired.
    cache_mod.clear()


def test_capacity_evicts_oldest():
    """超出容量淘汰最早插入（防内存无限涨）。Over capacity evicts the oldest entry
    (bounds memory)."""
    cache_mod.clear()
    cap = config.settings.rag.cache_max_entries
    for i in range(cap + 10):
        cache_mod.set(f"k{i}", [i])
    assert cache_mod.get("k0") is None            # 最旧的被挤掉。Oldest evicted.
    assert cache_mod.get(f"k{cap + 9}") == [cap + 9]
    cache_mod.clear()


def test_clear_empties_everything():
    cache_mod.clear()
    cache_mod.set("a", [1])
    cache_mod.clear()
    assert cache_mod.get("a") is None


def test_make_rag_key_normalizes_query():
    """查询归一化（小写+空白折叠）→ 同义查询同键；top_k 不同 → 不同键。
    Query normalization (lowercase + whitespace fold) → same key for equivalent
    queries; different top_k → different keys."""
    a = cache_mod.make_rag_key("  Python   版本 ", 12, 5)
    b = cache_mod.make_rag_key("python 版本", 12, 5)
    c = cache_mod.make_rag_key("python 版本", 12, 3)
    assert a == b
    assert a != c


def test_make_rag_key_binds_index_db(tmp_path, monkeypatch):
    """键绑定索引库路径——换库即换键（测试隔离 + 多库不串味）。
    The key binds to the index DB path — different DB, different key (test isolation)."""
    from core import rag as rag_mod
    monkeypatch.setattr(rag_mod, "INDEX_DB", tmp_path / "a.db")
    a = cache_mod.make_rag_key("q", 12, 5)
    monkeypatch.setattr(rag_mod, "INDEX_DB", tmp_path / "b.db")
    b = cache_mod.make_rag_key("q", 12, 5)
    assert a != b
