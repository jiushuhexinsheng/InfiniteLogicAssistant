# -*- coding: utf-8 -*-
"""长期事实记忆 — facts.sqlite

按 topic 合并去重（同主题覆盖内容、更新 ts）；FTS5 全文检索（trigram 分词适配中文）。
每操作短连接，线程安全。
"""
import sqlite3
from datetime import datetime
from pathlib import Path

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


class FactStore:
    def __init__(self, path: Path = FACTS_DB):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS facts ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "topic TEXT, content TEXT, source TEXT, ts TEXT)"
            )
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
        return sqlite3.connect(str(self.path))

    async def upsert(self, topic: str, content: str, source: str = "") -> None:
        ts = datetime.now().isoformat(timespec="seconds")
        with self._conn() as conn:
            cur = conn.execute("SELECT id FROM facts WHERE topic=?", (topic,))
            if cur.fetchone():
                conn.execute("UPDATE facts SET content=?, source=?, ts=? WHERE topic=?",
                             (content, source, ts, topic))
            else:
                conn.execute("INSERT INTO facts (topic, content, source, ts) VALUES (?,?,?,?)",
                             (topic, content, source, ts))

    async def get(self, topic: str) -> list[dict]:
        with self._conn() as conn:
            cur = conn.execute("SELECT topic, content, source, ts FROM facts WHERE topic=?", (topic,))
            return [dict(zip(("topic", "content", "source", "ts"), row)) for row in cur.fetchall()]

    async def search(self, keywords: list[str]) -> list[dict]:
        """FTS5 全文检索（bm25 排序）；<3 字符关键词回退子串扫描。"""
        out: list[dict] = []
        seen: set[str] = set()
        long_ks = [k for k in keywords if len(k) >= 3]
        with self._conn() as conn:
            if long_ks:
                q = " OR ".join(f'"{k}"' for k in long_ks)
                rows = conn.execute(
                    "SELECT f.topic, f.content, f.source, f.ts, bm25(facts_fts) AS score "
                    "FROM facts_fts JOIN facts f ON facts_fts.rowid = f.id "
                    "WHERE facts_fts MATCH ? ORDER BY score",
                    (q,),
                ).fetchall()
                for topic, content, source, ts, _score in rows:
                    seen.add(topic)
                    out.append({"topic": topic, "content": content, "source": source, "ts": ts})
            # 回退：短关键词 / FTS 未覆盖
            all_rows = conn.execute("SELECT topic, content, source, ts FROM facts").fetchall()
            for topic, content, source, ts in all_rows:
                if topic in seen:
                    continue
                blob = (topic + content).lower()
                if any(k.lower() in blob for k in keywords):
                    out.append({"topic": topic, "content": content, "source": source, "ts": ts})
        return out

    async def all(self) -> list[dict]:
        with self._conn() as conn:
            cur = conn.execute("SELECT topic, content, source, ts FROM facts ORDER BY ts DESC")
            return [dict(zip(("topic", "content", "source", "ts"), row)) for row in cur.fetchall()]

    async def delete(self, topic: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM facts WHERE topic=?", (topic,))
