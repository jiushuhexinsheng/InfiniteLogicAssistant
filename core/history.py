# -*- coding: utf-8 -*-
"""会话历史 — SQLite data/history.db，完整保存每轮对话（用户/助手/工具摘要）

会话结束时（state.persist）整段覆盖写入；控制台「历史」tab 列表/详情/删除。
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from core.config import ROOT_DIR

HISTORY_DB = ROOT_DIR / "data" / "history.db"


class HistoryStore:
    def __init__(self, path: Path = HISTORY_DB):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS conversations ("
                "id TEXT PRIMARY KEY, created TEXT, updated TEXT, status TEXT, summary TEXT)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS messages ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT, "
                "role TEXT, content TEXT, tool_calls TEXT, ts TEXT)"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id)")

    def _conn(self):
        return sqlite3.connect(str(self.path))

    async def save_conversation(self, conv_id: str, messages: list[dict],
                                status: str = "", summary: str = "") -> None:
        """整段覆盖保存一个会话的完整消息（会话结束时调用）。"""
        now = datetime.now().isoformat(timespec="milliseconds")
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO conversations (id, created, updated, status, summary) VALUES (?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET updated=excluded.updated, "
                "status=excluded.status, summary=excluded.summary",
                (conv_id, now, now, status, summary),
            )
            conn.execute("DELETE FROM messages WHERE conversation_id=?", (conv_id,))
            for m in messages:
                if not isinstance(m, dict):
                    continue
                tool_calls = json.dumps(m.get("tool_calls"), ensure_ascii=False) if m.get("tool_calls") else None
                conn.execute(
                    "INSERT INTO messages (conversation_id, role, content, tool_calls, ts) VALUES (?,?,?,?,?)",
                    (conv_id, m.get("role", ""), m.get("content", "") or "", tool_calls, now),
                )

    async def list_conversations(self, limit: int = 30) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT c.id, c.created, c.updated, c.status, c.summary, COUNT(m.id) "
                "FROM conversations c LEFT JOIN messages m ON c.id = m.conversation_id "
                "GROUP BY c.id ORDER BY c.updated DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {"id": r[0], "created": r[1], "updated": r[2], "status": r[3],
             "summary": r[4], "message_count": r[5]}
            for r in rows
        ]

    async def get_conversation(self, conv_id: str) -> dict | None:
        with self._conn() as conn:
            c = conn.execute(
                "SELECT id, created, updated, status, summary FROM conversations WHERE id=?", (conv_id,)
            ).fetchone()
            if not c:
                return None
            msgs = conn.execute(
                "SELECT role, content, tool_calls FROM messages WHERE conversation_id=? ORDER BY id", (conv_id,)
            ).fetchall()
        return {
            "id": c[0], "created": c[1], "updated": c[2], "status": c[3], "summary": c[4],
            "messages": [
                {"role": m[0], "content": m[1] or "",
                 "tool_calls": json.loads(m[2]) if m[2] else None}
                for m in msgs
            ],
        }

    async def delete(self, conv_id: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM messages WHERE conversation_id=?", (conv_id,))
            conn.execute("DELETE FROM conversations WHERE id=?", (conv_id,))


_history_store: HistoryStore | None = None


def get_history_store() -> HistoryStore:
    global _history_store
    if _history_store is None:
        _history_store = HistoryStore()
    return _history_store
