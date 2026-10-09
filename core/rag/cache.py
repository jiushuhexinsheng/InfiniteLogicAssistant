# -*- coding: utf-8 -*-
"""RAG 检索/精排结果缓存 — TTL + 容量上限，省掉重复查询的 BM25 重算与 rerank LLM 花费。

RAG retrieval/rerank result cache — TTL + capacity bound, saving repeated BM25
recomputation and rerank LLM spend (the LLM rerank tier charges per query).

- 只缓存**精排后的最终 hits**（build_context_with_sources 接线处写入），空结果也缓存
  （索引未建时免每次全扫），未命中返回 ``None`` 以区别于命中的空列表。
- ``make_rag_key`` 键绑定索引库路径 —— 换库即换键（测试隔离、多库不串味）；索引重建
  走 ``clear()``（indexer 末尾调用）+ TTL 双保险。
- 单进程 asyncio 内使用；竞态最坏是重复计算一次（无害），故不加锁。
"""
import time
from typing import TypeVar

from core import config

_T = TypeVar("_T")

# 参数已入配置（此前是本模块硬编码 TTL_S=300 / MAX_ENTRIES=128）：
# 结果保鲜期 rag.cache_ttl_s（过期重检以跟进索引变化）；容量 rag.cache_max_entries
# （按插入序淘汰最旧，防长期运行内存无限涨）。
# Both knobs now live in config (formerly the hardcoded TTL_S=300 / MAX_ENTRIES=128):
# freshness window rag.cache_ttl_s, capacity rag.cache_max_entries.
_store: dict[str, tuple[float, object]] = {}


def make_rag_key(query: str, *parts: object) -> str:
    """缓存键：归一化查询 + 调用方参数（fetch_n/top_k）+ 索引库路径。

    Cache key: normalized query + caller params (fetch_n/top_k) + index DB path.
    """
    from core import rag as rag_mod
    norm = " ".join((query or "").lower().split())
    return f"rag:{rag_mod.INDEX_DB}:{norm}:{':'.join(str(p) for p in parts)}"


def get(key: str) -> _T | None:
    """取缓存；过期/未命中返回 ``None``（与命中空列表 ``[]`` 区分）。类型随调用方注解推断。

    Fetch from cache; expired/missing returns ``None`` (distinct from a cached ``[]``).
    The type follows the caller's annotation.
    """
    ent = _store.get(key)
    if ent is None:
        return None
    ts, value = ent
    if time.monotonic() - ts >= config.settings.rag.cache_ttl_s:
        _store.pop(key, None)
        return None
    return value  # type: ignore[return-value]


def set(key: str, value: object) -> None:
    """写缓存；超容量按插入序淘汰最旧。Store; over capacity evicts the oldest."""
    if key in _store:
        _store.pop(key)  # 重新插队到最新。Re-insert as newest.
    _store[key] = (time.monotonic(), value)
    while len(_store) > config.settings.rag.cache_max_entries:
        _store.pop(next(iter(_store)))


def clear() -> None:
    """清空缓存（索引重建时调用）。Empty the cache (called on index rebuild)."""
    _store.clear()
