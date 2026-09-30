# -*- coding: utf-8 -*-
"""长期事实记忆 — facts.sqlite。Long-term fact memory — facts.sqlite.

**写入语义（ADD-only + 失效，docs/designs/04 §3.1，借鉴 mem0/Graphiti）**：
`upsert` 不再静默覆盖 —— 与现行有效行内容等价（trigram Jaccard ≥ 0.9）仅刷新 ts；
内容冲突则旧行标 `valid_until`（失效可查）后插入新行。历史不丢、来源不互踩
（voice 复述一条 task 事实不会偷走 `task:*` 来源）。

**检索**：FTS5 bm25 主路（trigram 分词适配中文）+ 子串回退；bm25 分数按新近度加权
（`memory.recency_weight` / `recency_half_life_days`，0 权重 = 纯 bm25），只返回
现行有效行；`limit` 控制注入条数。每操作短连接，线程安全。

Long-term fact memory — facts.sqlite. Writes follow **ADD-only + retire**
(docs/designs/04 §3.1, inspired by mem0/Graphiti): `upsert` no longer silently
overwrites — content equivalent to the active row (trigram Jaccard ≥ 0.9) only
refreshes ts; conflicting content retires the old row (`valid_until`, history
kept) and inserts a new one. History is preserved and sources stop clobbering
each other (a voice re-assert of a task fact no longer steals its `task:*`
source). Search: FTS5 bm25 main path (trigram tokenizer for Chinese) plus a
substring fallback, bm25 scores weighted by recency (`memory.recency_weight` /
`recency_half_life_days`; weight 0 = pure bm25), active rows only, `limit` caps
the injected count. Each operation uses a short-lived connection; thread-safe.
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from core import config
from core.config import ROOT_DIR

FACTS_DB = ROOT_DIR / "memory" / "facts.sqlite"

# FTS5 触发器同步：facts 的增删改自动维护 facts_fts（rowid = facts.id）
# 注意：trigram 分词对 <3 字符内容不产生 token，FTS5 的 'delete' 特殊命令会失败，
# 因此用普通 DELETE ... WHERE rowid（对任何分词器均有效）。
_FTS_SYNC = [
    "CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN "
    "INSERT INTO facts_fts(rowid, topic, content, source) VALUES (new.id, new.topic, new.content, new.source); END",
    "CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN "
    "DELETE FROM facts_fts WHERE rowid = old.id; END",
    "CREATE TRIGGER IF NOT EXISTS facts_au AFTER UPDATE ON facts BEGIN "
    "DELETE FROM facts_fts WHERE rowid = old.id; "
    "INSERT INTO facts_fts(rowid, topic, content, source) VALUES (new.id, new.topic, new.content, new.source); END",
]

# ADD-only 迁移（幂等：重复 ALTER 抛 OperationalError，逐条吞掉）。
# valid_until = 失效时间（NULL=现行有效）；path = 分层路径；origin = 溯源 JSON。
# ADD-only migration (idempotent: a duplicate ALTER raises OperationalError, swallowed
# per statement). valid_until = retirement time (NULL = active); path = hierarchy;
# origin = provenance JSON.
_MIGRATION = [
    "ALTER TABLE facts ADD COLUMN valid_until TEXT",
    "ALTER TABLE facts ADD COLUMN path TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE facts ADD COLUMN origin TEXT",
]

# 内容等价阈值（trigram Jaccard）：≥ 此值视为同一事实的复述 → 只刷新 ts。
# 与任务库 find_similar 同族的字符三元组算法（那边的注释解释了为何不用 bm25 阈值）。
# Content-equivalence threshold (trigram Jaccard): at or above it the row is a
# restatement of the same fact → only ts refreshes. Same character-trigram family
# as the task store's find_similar (its comments explain why not bm25 thresholds).
_EQUIV_THRESHOLD = 0.9

# 过期日志兜底。Fallback for unparsable timestamps.
_MAX_AGE_DAYS = 3650.0


def _trigrams(s: str) -> set[str]:
    """字符三元组集合（先剥空白；<3 字符整体作为一个三元组）。Character trigram set
    (whitespace stripped; strings shorter than 3 chars form one trigram).

    Args:
        s: 原文。Source text.

    Returns:
        三元组集合。The trigram set.
    """
    t = "".join(s.split()).lower()
    if len(t) < 3:
        return {t} if t else set()
    return {t[i:i + 3] for i in range(len(t) - 2)}


def _similarity(a: str, b: str) -> float:
    """两段文本的 trigram Jaccard 相似度（0~1）。Trigram Jaccard similarity of two
    texts (0..1).

    Args:
        a: 文本 A。Text A.
        b: 文本 B。Text B.

    Returns:
        相似度。Similarity.
    """
    ta, tb = _trigrams(a), _trigrams(b)
    if not ta or not tb:
        return 1.0 if ta == tb else 0.0
    return len(ta & tb) / len(ta | tb)


def _age_days(ts: str | None) -> float:
    """ts（ISO8601）距今天数；解析失败按 0（视作最新，加权不惩罚）。Days since ts
    (ISO8601); unparsable → 0 (treated as fresh, recency never punishes it).

    Args:
        ts: 时间戳字符串。Timestamp string.

    Returns:
        天数。Days.
    """
    if not ts:
        return 0.0
    try:
        dt = datetime.fromisoformat(ts)
        return max(0.0, (datetime.now() - dt).total_seconds() / 86400.0)
    except ValueError:
        return 0.0


def _recency_params() -> tuple[float, float]:
    """读取记忆新近度加权参数（热读，随配置热更）。Read the recency-weight parameters
    (hot read; follows config reload).

    Returns:
        (权重 w, 半衰期天数 τ)。(weight w, half-life days τ).
    """
    try:
        m = config.settings.memory
        return float(m.recency_weight), float(m.recency_half_life_days)
    except Exception:
        return 0.0, 30.0


class FactStore:
    """基于 SQLite + FTS5 的长期事实存储。Long-term fact store backed by SQLite + FTS5."""

    def __init__(self, path: Path = FACTS_DB):
        """打开 / 初始化数据库（建表、FTS5 索引、同步触发器、数据回填、ADD-only 迁移）。
        Open / initialize the database (tables, FTS5 index, sync triggers, backfill,
        ADD-only migration).

        Args:
            path: 数据库文件路径，默认 facts.sqlite。Database file path, defaults to facts.sqlite.
        """
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS facts ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "topic TEXT, content TEXT, source TEXT, ts TEXT)"
            )
            # ADD-only 新列（老库 ALTER；列已存在时吞掉）。
            # ADD-only columns (ALTER on old databases; duplicates swallowed).
            for ddl in _MIGRATION:
                try:
                    conn.execute(ddl)
                except sqlite3.OperationalError:
                    pass  # duplicate column name → 已迁移。Already migrated.
            # FTS5 索引：trigram 分词支持中文子串匹配（查询 ≥3 字符）
            conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5("
                "topic, content, source, tokenize='trigram')"
            )
            for ddl in _FTS_SYNC:
                conn.execute(ddl)
            # 已有数据回填（幂等：FTS 空才回填）
            n = conn.execute("SELECT count(*) FROM facts_fts").fetchone()[0]
            if n == 0:
                conn.execute(
                    "INSERT INTO facts_fts(rowid, topic, content, source) "
                    "SELECT id, topic, content, source FROM facts")

    def _conn(self):
        """开启一个短连接（每次操作独立，线程安全）。Open a short-lived connection (independent per operation; thread-safe).

        Returns:
            sqlite3 连接对象。A sqlite3 connection.
        """
        return sqlite3.connect(str(self.path))

    async def upsert(self, topic: str, content: str, source: str = "", *,
                     path: str = "", origin: dict | None = None) -> None:
        """ADD-only 协调写入（docs/designs/04 §3.1）。

        - 与现行有效行内容等价（trigram Jaccard ≥ 0.9）→ 仅刷新 ts（触达即新鲜，
          source/path/origin 保留原值 —— voice 复述不再偷走 task 来源）；
        - 内容冲突 → 旧行 `valid_until=now` 失效（历史可查），插入新行；
        - 无现行行 → 直接插入。

        Reconcile write in the ADD-only spirit (docs/designs/04 §3.1): content
        equivalent to the active row (trigram Jaccard ≥ 0.9) only refreshes ts
        (touch = freshness; source/path/origin stay — a voice re-assert no longer
        steals a task source); conflicting content retires the old row
        (`valid_until=now`, history kept) and inserts a new one; no active row →
        straight insert.

        Args:
            topic: 事实主题。Fact topic.
            content: 事实内容。Fact content.
            source: 来源标识（如 task:123 / voice）。Source identifier (e.g. task:123 / voice).
            path: 分层路径（如 偏好；空=未分类）。Hierarchy path (e.g. 偏好; empty = unclassified).
            origin: 溯源坐标（{conv_id, turn_id}）。Provenance ({conv_id, turn_id}).
        """
        ts = datetime.now().isoformat(timespec="seconds")
        origin_json = json.dumps(origin, ensure_ascii=False) if origin else None
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, content FROM facts "
                "WHERE topic=? AND valid_until IS NULL "
                "ORDER BY id DESC LIMIT 1",
                (topic,),
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO facts (topic, content, source, ts, path, origin) "
                    "VALUES (?,?,?,?,?,?)",
                    (topic, content, source, ts, path, origin_json),
                )
                return
            row_id, old_content = row
            if _similarity(old_content, content) >= _EQUIV_THRESHOLD:
                # 等价复述：只刷新触达时间。Equivalent restatement: refresh touch time only.
                conn.execute("UPDATE facts SET ts=? WHERE id=?", (ts, row_id))
                return
            # 冲突：失效旧行 + 插入新行（历史保留，来源不互踩）。
            # Conflict: retire the old row + insert the new one (history kept, sources
            # do not clobber each other).
            conn.execute("UPDATE facts SET valid_until=? WHERE id=?", (ts, row_id))
            conn.execute(
                "INSERT INTO facts (topic, content, source, ts, path, origin) "
                "VALUES (?,?,?,?,?,?)",
                (topic, content, source, ts, path, origin_json),
            )

    async def get(self, topic: str) -> list[dict]:
        """按主题精确查询**现行有效**记录。Query active records matching a topic exactly.

        Args:
            topic: 事实主题。Fact topic.

        Returns:
            记录 dict 列表（topic / content / source / ts / path / origin）。Record dicts.
        """
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT topic, content, source, ts, path, origin FROM facts "
                "WHERE topic=? AND valid_until IS NULL ORDER BY id DESC",
                (topic,),
            )
            return [dict(zip(("topic", "content", "source", "ts", "path", "origin"), row))
                    for row in cur.fetchall()]

    async def history(self, topic: str) -> list[dict]:
        """按主题查询**全部**记录含已失效（演变链，按 id 倒序）。Query all records for a
        topic including retired ones (the evolution chain, newest id first).

        Args:
            topic: 事实主题。Fact topic.

        Returns:
            记录 dict 列表（含 valid_until）。Record dicts (including valid_until).
        """
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT topic, content, source, ts, path, origin, valid_until FROM facts "
                "WHERE topic=? ORDER BY id DESC",
                (topic,),
            )
            return [dict(zip(("topic", "content", "source", "ts", "path", "origin",
                              "valid_until"), row)) for row in cur.fetchall()]

    async def search(self, keywords: list[str], limit: int | None = None) -> list[dict]:
        """FTS5 全文检索（bm25 × 新近度加权）；<3 字符关键词回退子串扫描；只返回现行有效行。

        新近度：`score' = score × (1 + w × 0.5 ** (age_days / τ))` —— bm25 为负值
        （越小越好），乘 >1 的新近系数使其更小 → 更新的事实排更前；w=0 退化纯 bm25。

        FTS5 full-text search (bm25 × recency weight); keywords shorter than 3
        characters fall back to substring scanning; active rows only. Recency:
        `score' = score × (1 + w * 0.5 ** (age_days / τ))` — bm25 is negative (lower
        is better), so multiplying by a >1 freshness factor ranks newer facts first;
        w = 0 degrades to pure bm25.

        Args:
            keywords: 关键词列表。Keyword list.
            limit: 返回条数上限（None=不限）。Cap on returned rows (None = no cap).

        Returns:
            按加权相关度排序的记录 dict 列表。Records sorted by weighted relevance.
        """
        w, tau = _recency_params()
        scored: list[tuple[float, dict]] = []
        seen: set[str] = set()
        long_ks = [k for k in keywords if len(k) >= 3]
        with self._conn() as conn:
            if long_ks:
                q = " OR ".join(f'"{k}"' for k in long_ks)
                rows = conn.execute(
                    "SELECT f.topic, f.content, f.source, f.ts, f.path, f.origin, "
                    "bm25(facts_fts) AS score "
                    "FROM facts_fts JOIN facts f ON facts_fts.rowid = f.id "
                    "WHERE facts_fts MATCH ? AND f.valid_until IS NULL",
                    (q,),
                ).fetchall()
                for topic, content, source, ts, path, origin, score in rows:
                    seen.add(topic)
                    factor = 1.0 + w * (0.5 ** (_age_days(ts) / tau) if tau > 0 else 1.0) if w else 1.0
                    scored.append((score * factor, {
                        "topic": topic, "content": content, "source": source,
                        "ts": ts, "path": path, "origin": origin,
                    }))
                scored.sort(key=lambda x: x[0])  # bm25 负值升序 = 相关度降序。Negative bm25 ascending = relevance descending.
            out = [row for _, row in scored]
            # 回退：短关键词 / FTS 未覆盖（无分数，接在打分行之后，保持旧行为）。
            # Fallback: short keywords / not FTS-covered (unscored; appended after the
            # scored rows, preserving legacy behaviour).
            all_rows = conn.execute(
                "SELECT topic, content, source, ts, path, origin FROM facts "
                "WHERE valid_until IS NULL"
            ).fetchall()
            for topic, content, source, ts, path, origin in all_rows:
                if topic in seen:
                    continue
                blob = (topic + content).lower()
                if any(k.lower() in blob for k in keywords):
                    out.append({"topic": topic, "content": content, "source": source,
                                "ts": ts, "path": path, "origin": origin})
        return out[:limit] if limit else out

    async def all(self) -> list[dict]:
        """按时间倒序返回全部**现行有效**事实。Return all active facts ordered by
        timestamp descending.

        Returns:
            记录 dict 列表。Record dicts.
        """
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT topic, content, source, ts, path, origin FROM facts "
                "WHERE valid_until IS NULL ORDER BY ts DESC"
            )
            return [dict(zip(("topic", "content", "source", "ts", "path", "origin"), row))
                    for row in cur.fetchall()]

    async def delete(self, topic: str) -> None:
        """按主题**硬删**全部匹配记录（用户显式清除 = 抹除，不留痕；系统性失效走
        valid_until）。Delete all records for a topic (an explicit user clear = purge,
        no trace; systemic retirement goes through valid_until).

        Args:
            topic: 事实主题。Fact topic.
        """
        with self._conn() as conn:
            conn.execute("DELETE FROM facts WHERE topic=?", (topic,))
