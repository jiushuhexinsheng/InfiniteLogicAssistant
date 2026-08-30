# -*- coding: utf-8 -*-
"""会话历史/存储 — SQLite data/history.db，完整保存每轮对话（用户/助手/工具摘要）

会话 = 可续接对话线（有稳定 id + name）：create_conversation / rename_conversation 管理，
save_conversation 按会话覆盖写消息（保留 name），控制台「历史/会话」tab 列表/详情/删除。
"""
import json
import sqlite3
import uuid
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
                "id TEXT PRIMARY KEY, name TEXT DEFAULT '', created TEXT, updated TEXT, "
                "status TEXT, summary TEXT, archived INTEGER DEFAULT 0)"
            )
            # 迁移：老库缺 name / archived 列 → 补列
            cols = [r[1] for r in conn.execute("PRAGMA table_info(conversations)").fetchall()]
            if "name" not in cols:
                conn.execute("ALTER TABLE conversations ADD COLUMN name TEXT DEFAULT ''")
            if "archived" not in cols:
                conn.execute("ALTER TABLE conversations ADD COLUMN archived INTEGER DEFAULT 0")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS messages ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT, "
                "role TEXT, content TEXT, tool_calls TEXT, ts TEXT)"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id)")

    def _conn(self):
        return sqlite3.connect(str(self.path))

    # ── 会话管理 ──

    async def create_conversation(self, name: str = "新会话") -> str:
        """新建会话，返回 id。"""
        cid = uuid.uuid4().hex[:12]
        now = datetime.now().isoformat(timespec="milliseconds")
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO conversations (id, name, created, updated) VALUES (?,?,?,?)",
                (cid, name, now, now),
            )
        return cid

    async def rename_conversation(self, conv_id: str, name: str) -> None:
        with self._conn() as conn:
            conn.execute("UPDATE conversations SET name=? WHERE id=?", (name, conv_id))

    async def clear_messages(self, conv_id: str) -> None:
        """清除上下文：清空会话消息（保留会话记录与 name）。"""
        with self._conn() as conn:
            conn.execute("DELETE FROM messages WHERE conversation_id=?", (conv_id,))

    async def set_archived(self, conv_id: str, archived: bool) -> None:
        with self._conn() as conn:
            conn.execute("UPDATE conversations SET archived=? WHERE id=?", (1 if archived else 0, conv_id))

    # ── 消息读写 ──

    async def save_conversation(self, conv_id: str, messages: list[dict],
                                status: str = "", summary: str = "") -> None:
        """整段覆盖保存一个会话的完整消息（会话结束时调用）。

        新会话 INSERT 用默认名「新会话」；已存在会话 UPDATE 时保留 name。
        """
        now = datetime.now().isoformat(timespec="milliseconds")
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO conversations (id, name, created, updated, status, summary) VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET updated=excluded.updated, "
                "status=excluded.status, summary=excluded.summary",
                (conv_id, "新会话", now, now, status, summary),
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

    async def list_conversations(self, limit: int = 30, archived: bool | None = False) -> list[dict]:
        """会话列表。

        archived=False（默认）排除归档 / True 只归档 / None 全部。
        """
        where = ""
        if archived is True:
            where = "WHERE c.archived = 1"
        elif archived is False:
            where = "WHERE c.archived = 0"
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT c.id, c.name, c.created, c.updated, c.status, c.summary, c.archived, COUNT(m.id) "
                f"FROM conversations c LEFT JOIN messages m ON c.id = m.conversation_id "
                f"{where} GROUP BY c.id ORDER BY c.updated DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {"id": r[0], "name": r[1], "created": r[2], "updated": r[3], "status": r[4] or "",
             "summary": r[5] or "", "archived": bool(r[6]), "message_count": r[7]}
            for r in rows
        ]

    async def get_conversation(self, conv_id: str) -> dict | None:
        with self._conn() as conn:
            c = conn.execute(
                "SELECT id, name, created, updated, status, summary, archived FROM conversations WHERE id=?", (conv_id,)
            ).fetchone()
            if not c:
                return None
            msgs = conn.execute(
                "SELECT role, content, tool_calls FROM messages WHERE conversation_id=? ORDER BY id", (conv_id,)
            ).fetchall()
        return {
            "id": c[0], "name": c[1], "created": c[2], "updated": c[3], "status": c[4] or "", "summary": c[5] or "",
            "archived": bool(c[6]),
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
    """返回容器持有的全局历史存储（测试可 monkeypatch 本函数）。"""
    from core.container import AppContext
    return AppContext.get().history_store()
