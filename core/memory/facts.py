# -*- coding: utf-8 -*-
"""长期事实记忆 — facts.sqlite

按 topic 合并去重（同主题覆盖内容、更新 ts）；关键词检索。
每操作短连接，线程安全。
"""
import sqlite3
from datetime import datetime
from pathlib import Path

from core.config import ROOT_DIR

FACTS_DB = ROOT_DIR / "memory" / "facts.sqlite"


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
        with self._conn() as conn:
            rows = conn.execute("SELECT topic, content, source, ts FROM facts").fetchall()
        out = []
        for topic, content, source, ts in rows:
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
