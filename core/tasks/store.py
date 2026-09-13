# -*- coding: utf-8 -*-
"""任务知识库 — 成功任务存档 + 相似任务检索（用于减少重复询问）。

Task knowledge base — archives successful tasks and retrieves similar ones (to reduce
repeated questions).

**为何是独立的第五套存储**（其余四套都不合适）：
- `memory/facts.sqlite` 以 topic 为主键且 upsert 是【覆盖式】，会丢历史；任务记录须只增不改
- `rag/index.db` 每次 `index_sources()` 全量 DELETE 重建，运行时记录会被抹掉
- `data/history.db` 是会话形状，与「任务」不是同一实体
- `data/tasks/*.json` 单会话一个文件、无索引，无法按 goal 相似度检索

**为何不用 FTS5**：库规模是几百条量级，全表扫描代价可忽略；而 bm25 的分数量纲依赖
数据规模，拿它当「够不够相似」的阈值不稳。改用与规模无关的字符 trigram Jaccard。

**Why a separate fifth store** (none of the existing four fit): the facts store is keyed
by topic with overwrite semantics and would lose history; the RAG index is fully rebuilt
on every `index_sources()` call; `history.db` is conversation-shaped; `data/tasks/*.json`
has no index. **Why no FTS5**: the library is a few hundred rows, so a full scan is
cheap, while bm25's score scale depends on corpus size and makes a poor similarity
threshold. Character-trigram Jaccard is scale-independent.
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from core.config import ROOT_DIR

TASKS_DB = ROOT_DIR / "memory" / "tasks.sqlite"

# 相似度阈值：低于此值 find_similar 返回 None（不预填）。
# 这是「不误预填」的闸门，不要为了提升命中率把它放宽。
# Similarity threshold: below it find_similar returns None. This is the gate that prevents
# prefilling parameters from an unrelated task; do not relax it just to raise the hit rate.
SIMILARITY_THRESHOLD = 0.5

# 单个字符串参数超过此长度即截断（避免把当时的文件内容整份留在库里）。
# Strings longer than this in a tool argument are truncated, so a whole file's contents do
# not end up persisted in the task library.
_MAX_ARG_CHARS = 200


def _trigrams(s: str) -> set[str]:
    """字符级三元组（先剥空白）。Character-level trigrams (whitespace stripped first).

    Args:
        s: 输入字符串。The input string.

    Returns:
        三元组集合。The set of trigrams.
    """
    s = "".join(s.split())
    if not s:
        return set()
    return {s[i:i + 3] for i in range(len(s) - 2)} if len(s) >= 3 else {s}


def similarity(a: str, b: str) -> float:
    """两个字符串的 trigram Jaccard 相似度（0..1）。

    Trigram Jaccard similarity between two strings (0..1).

    Args:
        a: 字符串甲。First string.
        b: 字符串乙。Second string.

    Returns:
        相似度。The similarity score.
    """
    ta, tb = _trigrams(a), _trigrams(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _truncate_args(args: Any) -> Any:
    """截断工具参数里的长字符串值，并加标记。

    参数含 `write_file(content=...)`、`run_shell_tool(command=...)`；不截断会把当时的
    文件内容整份留在库里。非字符串值原样保留。

    Truncate long string values inside tool arguments and mark them. Arguments include
    `write_file(content=...)`; without truncation a whole file's contents would be
    persisted. Non-string values pass through unchanged.

    Args:
        args: 工具参数（或其嵌套值）。The tool arguments (or a nested value).

    Returns:
        截断后的结构。The truncated structure.
    """
    if isinstance(args, str):
        return args if len(args) <= _MAX_ARG_CHARS else args[:_MAX_ARG_CHARS] + "…(已截断)"
    if isinstance(args, dict):
        return {k: _truncate_args(v) for k, v in args.items()}
    if isinstance(args, list):
        return [_truncate_args(v) for v in args]
    return args


class TaskStore:
    """成功任务存档（只增不改）+ 相似任务检索。

    Archive of successful tasks (append-only) with similarity search.
    """

    def __init__(self, path: Path = TASKS_DB):
        """打开 / 初始化数据库（建表 + created 索引）。

        Open / initialize the database (create the table and the created index).

        Args:
            path: 数据库文件路径，默认 tasks.sqlite。Database file path.
        """
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS tasks ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "goal TEXT NOT NULL, params_json TEXT NOT NULL, steps_json TEXT NOT NULL,"
                "status TEXT NOT NULL, created TEXT NOT NULL, session_id TEXT)"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created DESC)")

    def _conn(self):
        """开启一个短连接（每次操作独立，线程安全）。Open a short-lived connection (thread-safe).

        Returns:
            sqlite3 连接。A sqlite3 connection.
        """
        return sqlite3.connect(str(self.path))

    async def record(self, task: Any, result: dict, session_id: str = "") -> None:
        """存档一条成功任务（只增不改）。

        Archive one successful task (append-only).

        Args:
            task: 已完成的任务。The finished task.
            result: 执行结果（取其 steps）。The execution result (its steps are stored).
            session_id: 来源会话 id。The originating session id.
        """
        steps = _truncate_args(list(result.get("steps") or []))
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO tasks(goal, params_json, steps_json, status, created, session_id) "
                "VALUES(?,?,?,?,?,?)",
                (
                    getattr(task, "goal", ""),
                    json.dumps(getattr(task, "params", {}) or {}, ensure_ascii=False, default=str),
                    json.dumps(steps, ensure_ascii=False, default=str),
                    str(result.get("status") or ""),
                    getattr(task, "created", "") or datetime.now().isoformat(),
                    session_id,
                ),
            )

    async def find_similar(self, goal: str, threshold: float = SIMILARITY_THRESHOLD) -> dict | None:
        """找出与 goal 最相似、且超过阈值的历史任务。

        低于阈值返回 None —— 这是「不误预填」的闸门：宁可少预填，不可按不相关的
        历史任务填错参数。

        Find the most similar archived task above the threshold. Below it returns None:
        the gate that prefers missing a prefill over prefilling from an unrelated task.

        Args:
            goal: 目标任务。The target goal.
            threshold: 相似度阈值。The similarity threshold.

        Returns:
            {"id","goal","params","created"} 或 None。The best match, or None.
        """
        best: dict | None = None
        best_score = 0.0
        for row in await self.list_tasks(limit=1000):
            score = similarity(goal, row["goal"])
            if score > best_score:
                best, best_score = row, score
        if best is None or best_score < threshold:
            return None
        return {"id": best["id"], "goal": best["goal"], "params": best["params"],
                "created": best["created"]}

    async def list_tasks(self, limit: int = 50) -> list[dict]:
        """按存档时间倒序列出任务。List archived tasks, newest first.

        Args:
            limit: 最多返回条数。Maximum number of rows.

        Returns:
            任务列表。The task list.
        """
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, goal, params_json, steps_json, status, created, session_id "
                "FROM tasks ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row(r) for r in rows]

    async def get_task(self, task_id: int) -> dict | None:
        """按 id 取单条任务详情。Fetch one archived task by id.

        Args:
            task_id: 任务 id。The task id.

        Returns:
            任务详情或 None。The task, or None.
        """
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, goal, params_json, steps_json, status, created, session_id "
                "FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        return self._row(row) if row else None

    async def delete_task(self, task_id: int) -> None:
        """删除一条任务存档。Delete one archived task.

        Args:
            task_id: 任务 id。The task id.
        """
        with self._conn() as conn:
            conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))

    @staticmethod
    def _row(row) -> dict:
        """行 → 字典（解析 JSON 列）。Row to dict (JSON columns parsed).

        Args:
            row: sqlite3 行。A sqlite3 row.

        Returns:
            任务字典。The task dict.
        """
        return {
            "id": row[0], "goal": row[1],
            "params": json.loads(row[2] or "{}"),
            "steps": json.loads(row[3] or "[]"),
            "status": row[4], "created": row[5], "session_id": row[6],
        }
