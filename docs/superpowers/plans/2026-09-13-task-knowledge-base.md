# 任务知识库 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 任务模式下完成时询问「完成了吗」，把成功任务存档；下次遇到相似目标时用历史参数预填，减少重复询问。

**Architecture:** 新增独立的 `core/tasks/store.py`（普通表 + 字符 trigram Jaccard 相似度，不用 FTS5）。`pipeline` 加两个钩子：澄清前用 `find_similar` 预填（**必须以 `confirmed` 重新 `form_task`，否则 `missing` 不会变小**），执行成功后按模式发完成确认、答「完成了」才存档。前端加 `[对话][任务]` 模式开关与「任务库」tab。

**Tech Stack:** Python 3.14 / FastAPI / pydantic v2 / sqlite3 / pytest / mypy；Vue 3.4 + TypeScript + Vite 5 / vue-tsc / Vitest 4。

**Spec:** `docs/superpowers/specs/2026-09-13-task-knowledge-base-design.md`

## Global Constraints

- 后端新增/修改的 docstring 必须**中英双语**；前端注释同样双语。
- **`similarity` 用字符 trigram Jaccard，阈值 0.5**；**低于阈值 `find_similar` 必须返回 None**（这是「不误预填」的闸门，不要为了提升命中率把它放宽）。
- **预填必须发生在 `missing` 产生之前** —— 用历史参数作为 `confirmed` **重新** `form_task`。若只在 `run_clarify` 之前填 `task.params`，`missing` 已算好、不会变小，功能等于白做。
- **`steps` 里的长字符串参数必须截断**（`_truncate_args`，>200 字符）：参数含 `write_file(content=...)`，不截断会把当时的文件内容整份留在库里。
- **`mode` 缺省 `"chat"`**：老前端不带该字段时行为完全不变（不询问完成、不预填）。
- **新增 API 端点会改 openapi** → 必须与 schema 变更**同一个 commit** 重新生成 `web/src/api/generated.ts`（CI 的 `gen:api` 门禁会校验）。
- **注意 `core/api/schemas.py` 存在与其它模块重复的手工模型**（`VadConfig` 那次踩过）：新增响应模型时先 `grep` 确认没有同名类。
- **`TaskStore` 的方法写成 `async def`**（内部是同步 sqlite3 短连接）—— 与 `core/memory/facts.py` 的 `FactStore` 保持一致。
- 后端验证：`python -m pytest tests/ -q` + `python -m mypy core/ server.py`；前端：`cd web && npm test` + `npm run build`。
- TDD：先写失败测试 → 运行确认失败 → 最小实现 → 运行确认通过 → 提交。
- 每个 Task 结束跑**全量**回归（历史上循环导入只在全量下复现）。

---

## 文件结构

| 文件 | 职责 | 动作 |
|---|---|---|
| `core/tasks/__init__.py` | 包导出 | Create |
| `core/tasks/store.py` | `TaskStore` + `similarity` + `_truncate_args` | Create |
| `core/orchestrator/task.py` | `Task.created` 时间戳 | Modify |
| `core/api/schemas.py` | 任务库响应模型 | Modify |
| `core/api/library.py` | 任务库路由（列表 / 详情 / 删除） | Create |
| `server.py` | 挂载新路由 | Modify |
| `core/orchestrator/pipeline.py` | 两个钩子（预填 / 完成确认+存档）+ `mode` 参数 | Modify |
| `core/api/voice.py` | `/voice/utter` 接收 `mode` | Modify |
| `web/src/api/generated.ts` | 重新生成 | Modify |
| `web/src/composables/assistant/store.ts` | `assistantMode` 单例 + localStorage | Modify |
| `web/src/components/layout/AppHeader.vue` | `[对话][任务]` 开关 | Modify |
| `web/src/api.ts` / `useChat.ts` | utter 请求体带 `mode` | Modify |
| `web/src/components/console/ConsoleLibrary.vue` | 任务库视图 | Create |
| `web/src/composables/useConsole.ts` | `CONSOLE_TABS` 加「任务库」 | Modify |
| `web/src/views/ConsolePage.vue` | 挂载任务库视图 | Modify |

---

## Task 1: `core/tasks/store.py`（相似度 + 截断 + CRUD）

**Files:**
- Create: `core/tasks/__init__.py`、`core/tasks/store.py`
- Test: `tests/test_tasks_store.py`

**Interfaces:**
- Consumes: `core.config.ROOT_DIR`
- Produces: `TASKS_DB: Path`；`TaskStore(path=TASKS_DB)`，方法 `async record(task, result, session_id="") -> None`、`async find_similar(goal, threshold=0.5) -> dict | None`、`async list_tasks(limit=50) -> list[dict]`、`async get_task(task_id) -> dict | None`、`async delete_task(task_id) -> None`；模块级 `similarity(a, b) -> float`、`_truncate_args(args) -> dict`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_tasks_store.py`：

```python
# -*- coding: utf-8 -*-
"""任务知识库存储（TaskStore / similarity / 参数截断）的测试。
Tests for the task knowledge base store (TaskStore / similarity / argument truncation).
"""
import pytest

from core.orchestrator.task import Task
from core.tasks.store import TaskStore, _truncate_args, similarity


# ─── similarity：字符 trigram Jaccard ───

def test_similarity_identical():
    """完全相同 = 1.0。Identical strings score 1.0."""
    assert similarity("复制文件到下载", "复制文件到下载") == 1.0


def test_similarity_no_overlap():
    """完全无交集 = 0.0。Disjoint strings score 0.0."""
    assert similarity("复制文件", "查询天气") == 0.0


def test_similarity_partial_between_zero_and_one():
    """部分重叠落在 (0,1) 开区间。Partial overlap lands strictly between 0 and 1."""
    s = similarity("把 readme 复制到下载", "把 readme 复制到桌面")
    assert 0.0 < s < 1.0


def test_similarity_ignores_whitespace():
    """空白差异不影响判定（内部先剥空白）。Whitespace differences do not affect the score."""
    assert similarity("复制 文件", "复制文件") == 1.0


def test_similarity_short_and_empty():
    """短于 3 字符走单元素分支；空串为 0.0。Short strings use the single-element branch; empty is 0.0."""
    assert similarity("ab", "ab") == 1.0
    assert similarity("ab", "cd") == 0.0
    assert similarity("", "复制文件") == 0.0


# ─── _truncate_args：隐私处置 ───

def test_truncate_short_string_untouched():
    """短字符串原样保留。Short strings are left untouched."""
    assert _truncate_args({"path": "a.txt"}) == {"path": "a.txt"}


def test_truncate_long_string_marked():
    """超长字符串被截断并带标记 —— 避免把当时的文件内容整份留在库里。
    Over-long strings are truncated and marked, so a whole file's contents do not end up
    persisted in the task library."""
    long = "x" * 500
    out = _truncate_args({"content": long})
    assert len(out["content"]) < 500
    assert out["content"].startswith("x" * 200)
    assert "截断" in out["content"]


def test_truncate_keeps_non_strings():
    """非字符串值不受影响。Non-string values are unaffected."""
    assert _truncate_args({"n": 42, "b": True, "lst": [1, 2], "none": None}) == {
        "n": 42, "b": True, "lst": [1, 2], "none": None}


# ─── TaskStore CRUD 与阈值闸门 ───

def _task(goal: str, params: dict | None = None) -> Task:
    return Task(id="t1", goal=goal, params=params or {}, risk="read")


def _result() -> dict:
    return {"status": "done", "summary": "完成", "steps": [
        {"step": 0, "tool": "write_file", "args": {"path": "a.txt", "content": "y" * 500}, "status": "ok"},
    ]}


@pytest.fixture
def store(tmp_path):
    return TaskStore(tmp_path / "tasks.sqlite")


@pytest.mark.asyncio
async def test_record_and_list(store):
    """存档后可列出；steps 里的长参数已被截断。A recorded task is listed, with long step args truncated."""
    await store.record(_task("复制文件到下载", {"src": "a", "dest": "b"}), _result(), session_id="s1")
    rows = await store.list_tasks()
    assert len(rows) == 1
    assert rows[0]["goal"] == "复制文件到下载"
    assert rows[0]["params"] == {"src": "a", "dest": "b"}
    assert "截断" in rows[0]["steps"][0]["args"]["content"]


@pytest.mark.asyncio
async def test_find_similar_above_threshold(store):
    """相似度达阈值 → 返回最高分那条（含 params）。A hit above the threshold returns the best match with its params."""
    await store.record(_task("把 readme.txt 复制到下载目录", {"dest": "下载"}), _result())
    hit = await store.find_similar("把 readme.txt 复制到下载目录")
    assert hit is not None
    assert hit["params"] == {"dest": "下载"}


@pytest.mark.asyncio
async def test_find_similar_below_threshold_returns_none(store):
    """相似度低于阈值必须返回 None —— 这是「不误预填」的闸门。
    Below the threshold find_similar must return None: this is the gate that prevents
    prefilling parameters from an unrelated task."""
    await store.record(_task("把 readme.txt 复制到下载目录", {"dest": "下载"}), _result())
    assert await store.find_similar("导出上季度财务报表为 PDF") is None


@pytest.mark.asyncio
async def test_find_similar_on_empty_store(store):
    """空库返回 None。An empty store returns None."""
    assert await store.find_similar("随便什么目标") is None


@pytest.mark.asyncio
async def test_get_and_delete(store):
    """按 id 取详情与删除。Fetch by id and delete."""
    await store.record(_task("任务甲"), _result())
    rows = await store.list_tasks()
    tid = rows[0]["id"]
    assert (await store.get_task(tid))["goal"] == "任务甲"
    await store.delete_task(tid)
    assert await store.get_task(tid) is None
    assert await store.list_tasks() == []


@pytest.mark.asyncio
async def test_record_is_append_only(store):
    """同一 goal 存档两次保留两条 —— 只增不改是本表相对 facts 覆盖式的关键差异。
    Recording the same goal twice keeps both rows: append-only is the key difference from
    the facts store's overwrite semantics."""
    await store.record(_task("同一目标"), _result())
    await store.record(_task("同一目标"), _result())
    assert len(await store.list_tasks()) == 2
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_tasks_store.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.tasks'`

- [ ] **Step 3: 实现**

新建 `core/tasks/__init__.py`：

```python
# -*- coding: utf-8 -*-
"""任务知识库：成功任务存档与相似任务检索。
Task knowledge base: archives successful tasks and retrieves similar ones.
"""
from core.tasks.store import TASKS_DB, TaskStore, similarity

__all__ = ["TASKS_DB", "TaskStore", "similarity"]
```

新建 `core/tasks/store.py`：

```python
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

**Why a separate fifth store** (none of the existing four fit): the facts store is keyed by
topic with overwrite semantics and would lose history; the RAG index is fully rebuilt on
every `index_sources()` call; `history.db` is conversation-shaped; `data/tasks/*.json` has
no index. **Why no FTS5**: the library is a few hundred rows, so a full scan is cheap,
while bm25's score scale depends on corpus size and makes a poor similarity threshold.
Character-trigram Jaccard is scale-independent.
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
    return {s[i:i + 3] for i in range(len(s) - 2)} if len(s) >= 3 else ({s} if s else set())


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
        args: 工具参数字典（或其嵌套值）。The tool arguments (or a nested value).

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
    """成功任务存档（只增不改）+ 相似任务检索。Archive of successful tasks (append-only) with similarity search."""

    def __init__(self, path: Path = TASKS_DB):
        """打开 / 初始化数据库（建表 + created 索引）。Open / initialize the database.

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
        """开启一个短连接（每次操作独立，线程安全）。Open a short-lived connection (thread-safe)."""
        return sqlite3.connect(str(self.path))

    async def record(self, task: Any, result: dict, session_id: str = "") -> None:
        """存档一条成功任务。Archive one successful task.

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
                    task.goal,
                    json.dumps(task.params, ensure_ascii=False, default=str),
                    json.dumps(steps, ensure_ascii=False, default=str),
                    str(result.get("status") or ""),
                    datetime.now().isoformat(),
                    session_id,
                ),
            )

    async def find_similar(self, goal: str, threshold: float = SIMILARITY_THRESHOLD) -> dict | None:
        """找出与 goal 最相似且超过阈值的历史任务。

        Find the most similar archived task above the threshold.

        Args:
            goal: 目标任务。The target goal.
            threshold: 相似度阈值。The similarity threshold.

        Returns:
            {"id","goal","params","created"} 或 None（无命中 / 最高分不足）。The best match, or None.
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
        """删除一条任务。Delete one archived task.

        Args:
            task_id: 任务 id。The task id.
        """
        with self._conn() as conn:
            conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))

    @staticmethod
    def _row(row) -> dict:
        """行 → 字典（解析 JSON 列）。Row to dict (JSON columns parsed)."""
        return {
            "id": row[0], "goal": row[1],
            "params": json.loads(row[2] or "{}"),
            "steps": json.loads(row[3] or "[]"),
            "status": row[4], "created": row[5], "session_id": row[6],
        }
```

- [ ] **Step 4: 运行确认通过 + 全量后端回归**

Run: `python -m pytest tests/test_tasks_store.py -q && python -m pytest tests/ -q && python -m mypy core/ server.py`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add core/tasks tests/test_tasks_store.py
git commit -m "feat(任务库): 成功任务存档 + 相似检索（普通表 + trigram Jaccard）

独立第五套存储，理由写在模块 docstring：facts 是覆盖式会丢历史、rag 每次全量
重建、history 是会话形状、data/tasks/*.json 无索引。

不用 FTS5：库规模几百条，全表扫描可忽略；而 bm25 分数量纲依赖数据规模，
当相似度阈值不稳。改用与规模无关的字符 trigram Jaccard（阈值 0.5）。

_truncate_args 截断 steps 里的长字符串参数（>200 字符）—— 参数含
write_file(content=...)，不截断会把当时的文件内容整份留在库里。"
```

---

## Task 2: `Task.created` 时间戳

**Files:**
- Modify: `core/orchestrator/task.py`（`Task` dataclass 约 39-51 行、`form_task` 的构造约 82-88 行与兜底约 71 行）
- Test: `tests/test_orchestrator_task.py`

**Interfaces:**
- Consumes: 无
- Produces: `Task.created: str`（ISO 字符串，缺省空串）

- [ ] **Step 1: 写失败测试**

在 `tests/test_orchestrator_task.py` 追加：

```python
@pytest.mark.asyncio
async def test_form_task_sets_created_timestamp(monkeypatch):
    """form_task 给任务打上创建时间戳（任务库存档需要）。
    form_task stamps the task with a creation timestamp (the task library needs it)."""
    fake = _FakeLLM([[_done_with_form("复制文件", {"src": "a"}, [], "write")]])
    monkeypatch.setattr("core.orchestrator.task.get_llm_client", lambda: fake)
    t = await form_task(IntentResult(type="task", summary="复制"))
    assert t.created                      # 非空
    assert t.created[:4] == "2026" or t.created[:2] == "20"   # ISO 形如 20xx-...


def test_task_created_defaults_empty():
    """直接构造的 Task 时间戳缺省为空串（不破坏既有测试的构造方式）。
    A directly constructed Task defaults to an empty timestamp."""
    assert Task("t", "目标", risk="read").created == ""
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_orchestrator_task.py -q -k created`
Expected: FAIL — `AttributeError: 'Task' object has no attribute 'created'`

- [ ] **Step 3: 实现**

`core/orchestrator/task.py` —— 顶部确保 `from datetime import datetime`（若无则加），`Task` 加字段：

```python
    state: str = "queued"  # queued/planning/running/waiting_question/waiting_confirm/done/failed/stopped
    # 创建时间（ISO 字符串）：任务库存档用。Creation timestamp (ISO string) for the task library.
    created: str = ""
```

`form_task` 的两处构造补上 `created=datetime.now().isoformat()`：

```python
    fallback = Task(id=uuid.uuid4().hex[:12], goal=intent.summary, params={}, missing=[], risk="read",
                    created=datetime.now().isoformat())
```
```python
                return Task(
                    id=uuid.uuid4().hex[:12],
                    goal=str(data.get("goal") or intent.summary),
                    params=dict(data.get("params") or {}),
                    missing=parse_missing(data.get("missing")),
                    risk=risk,
                    created=datetime.now().isoformat(),
                )
```

- [ ] **Step 4: 运行确认通过 + 全量后端回归**

Run: `python -m pytest tests/ -q && python -m mypy core/ server.py`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add core/orchestrator/task.py tests/test_orchestrator_task.py
git commit -m "feat(任务): Task 加 created 时间戳（任务库存档需要）"
```

---

## Task 3: 任务库 API + 类型重生成

> **本任务把「新增端点」与「类型重生成」绑在一起**：新增 `response_model` 会改 openapi，
> CI 的 `gen:api` 门禁会校验 —— 分两个 commit 会让中间那个失败。

**Files:**
- Modify: `core/api/schemas.py`（新增响应模型）
- Create: `core/api/library.py`
- Modify: `server.py`（挂载路由）
- Modify: `web/src/api/generated.ts`（重新生成）
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: Task 1 的 `TaskStore`
- Produces: `GET /api/library` → `{ok, tasks:[...]}`；`GET /api/library/{id}` → `{ok, task}`；`DELETE /api/library/{id}` → `{ok}`

- [ ] **Step 1: 写失败测试**

在 `tests/test_server.py` 追加：

```python
def test_library_list_and_delete(client, tmp_path, monkeypatch):
    """任务库列表与删除端点。The task-library list and delete endpoints."""
    from core.tasks import store as store_mod
    monkeypatch.setattr(store_mod, "TASKS_DB", tmp_path / "lib.sqlite")
    import core.api.library as lib

    st = store_mod.TaskStore(tmp_path / "lib.sqlite")
    monkeypatch.setattr(lib, "_get_store", lambda: st)

    r = client.get("/api/library")
    assert r.status_code == 200
    assert r.json()["tasks"] == []

    import asyncio
    from core.orchestrator.task import Task
    asyncio.run(st.record(Task("t", "复制文件", {"dest": "下载"}, risk="read"),
                          {"status": "done", "steps": []}, session_id="s1"))

    r = client.get("/api/library")
    tasks = r.json()["tasks"]
    assert len(tasks) == 1 and tasks[0]["goal"] == "复制文件"

    tid = tasks[0]["id"]
    assert client.get(f"/api/library/{tid}").json()["task"]["params"] == {"dest": "下载"}
    assert client.delete(f"/api/library/{tid}").status_code == 200
    assert client.get("/api/library").json()["tasks"] == []
    assert client.get("/api/library/999999").status_code == 404
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_server.py -q -k library`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.api.library'`

- [ ] **Step 3: 实现**

先在 `core/api/schemas.py` 里 `grep` 确认没有同名类（**该文件存在与其它模块重复的手工模型，历史上踩过**）：

```bash
grep -n "class TaskLibraryItem\|class LibraryListResponse" core/api/schemas.py || echo "无同名类 ✓"
```

然后在 `schemas.py` 追加：

```python
class TaskLibraryItem(BaseModel):
    """任务库条目（一次成功任务的存档）。One archived successful task."""

    id: int
    goal: str
    params: dict[str, Any] = {}
    steps: list[Any] = []
    status: str = ""
    created: str = ""
    session_id: str = ""


class LibraryListResponse(ApiResponse):
    """任务库列表响应。The task-library list response."""

    tasks: list[TaskLibraryItem] = []


class LibraryDetailResponse(ApiResponse):
    """任务库详情响应。The task-library detail response."""

    task: TaskLibraryItem
```

新建 `core/api/library.py`：

```python
# -*- coding: utf-8 -*-
"""任务库 API — 成功任务存档的浏览与删除。

Task library API — browsing and deleting archived successful tasks.
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from core.api.schemas import ApiResponse, LibraryDetailResponse, LibraryListResponse
from core.tasks.store import TaskStore

router = APIRouter()

_store: TaskStore | None = None


def _get_store() -> TaskStore:
    """懒加载单例。Lazily created singleton.

    Returns:
        任务库存储。The task store.
    """
    global _store
    if _store is None:
        _store = TaskStore()
    return _store


@router.get("/library", response_model=LibraryListResponse)
async def library_list():
    """列出已存档的成功任务（按时间倒序）。

    List archived successful tasks, newest first.
    """
    return {"ok": True, "tasks": await _get_store().list_tasks()}


@router.get("/library/{task_id}", response_model=LibraryDetailResponse)
async def library_detail(task_id: int):
    """取单条任务详情。

    Fetch one archived task.
    """
    task = await _get_store().get_task(task_id)
    if task is None:
        return JSONResponse({"ok": False, "error": f"任务 {task_id} 不存在"}, status_code=404)
    return {"ok": True, "task": task}


@router.delete("/library/{task_id}", response_model=ApiResponse)
async def library_delete(task_id: int):
    """删除一条任务存档。

    Delete one archived task.
    """
    await _get_store().delete_task(task_id)
    return {"ok": True}
```

`server.py` 的 import 行与挂载处各加一处：

```python
from core.api import history, library, memory, providers, schedule, sessions, settings, tools, voice
```
```python
app.include_router(library.router, prefix="/api")
```

- [ ] **Step 4: 运行确认通过 + 重新生成类型**

Run: `python -m pytest tests/ -q && python -m mypy core/ server.py`
Expected: 全部通过

Run:
```bash
cd web && PYTHONIOENCODING=utf-8 python ../scripts/gen_openapi.py && npx --yes openapi-typescript@7.13.0 src/api/openapi.json -o src/api/generated.ts
cd .. && git diff --stat web/src/api/generated.ts
```
Expected: diff 非空（新增 `TaskLibraryItem` / `LibraryListResponse` / `LibraryDetailResponse`）

- [ ] **Step 5: 提交**

```bash
git add core/api/schemas.py core/api/library.py server.py tests/test_server.py web/src/api/generated.ts
git commit -m "feat(API): 任务库端点（列表/详情/删除）+ 同步前端类型

新增 response_model 会改 openapi，故 generated.ts 必须同 commit 重新生成
（CI 的 gen:api 门禁会校验）。
新增模型前先 grep 确认无同名类 —— core/api/schemas.py 存在与其它模块重复的
手工模型，历史上踩过（VadConfig 那次只改配置模型，字段被 response_model
静默过滤、前端收不到）。"
```

---

## Task 4: pipeline 预填钩子（减少询问）

**Files:**
- Modify: `core/orchestrator/pipeline.py`（`form_task` 之后、`run_clarify` 之前，约 170-172 行）
- Test: `tests/test_orchestrator_pipeline.py`

**Interfaces:**
- Consumes: Task 1 的 `TaskStore.find_similar`
- Produces: 无新接口；澄清前会用历史参数预填

- [ ] **Step 1: 写失败测试**

在 `tests/test_orchestrator_pipeline.py` 追加：

```python
@pytest.mark.asyncio
async def test_pipeline_prefills_params_from_similar_task(monkeypatch):
    """命中相似历史任务时，以历史参数作为 confirmed 重新 form_task（这样 missing 才会变小），
    并发出 notify 让用户看到。

    On a similar historical hit, form_task is re-run with the historical params as
    `confirmed` (only then does `missing` shrink) and a notify is emitted so the user sees it.
    """
    from core.orchestrator import pipeline as pl
    from core.orchestrator.control import StopController
    from core.orchestrator.intent import IntentResult
    from core.orchestrator.session import Session
    from core.orchestrator.task import MissingItem, Task

    calls: list = []

    async def fake_form(intent, confirmed=None):
        calls.append(confirmed)
        if confirmed:
            # 第二次（带历史参数）：missing 变空
            return Task(id="t2", goal="复制文件", params=dict(confirmed), missing=[], risk="read")
        return Task(id="t1", goal="复制文件", params={}, missing=[MissingItem(question="目标位置？")], risk="read")

    async def fake_find(goal, **kw):
        return {"id": 1, "goal": goal, "params": {"dest": "下载"}, "created": "2026-09-13"}

    monkeypatch.setattr(pl, "form_task", fake_form)
    monkeypatch.setattr(pl, "find_similar", fake_find)
    monkeypatch.setattr(pl, "judge_intent", _fake_judge)
    monkeypatch.setattr(pl, "execute_task", _fake_execute)
    monkeypatch.setattr(pl, "extract_and_store", lambda *a, **k: _noop())
    monkeypatch.setattr(pl, "get_facts_store", lambda: object())

    s = Session()
    events: asyncio.Queue = asyncio.Queue()
    await pl.run_pipeline("复制文件", s, events, StopController())

    assert calls == [None, {"dest": "下载"}], "第二次调用必须带 confirmed（历史参数）"
    assert s.task.params == {"dest": "下载"}
    # 用户能看到「参考了历史任务」
    notes = [e.get("text", "") for e in _drain(events) if e.get("type") == "task_state"]
    assert any("历史任务" in t for t in notes)


@pytest.mark.asyncio
async def test_pipeline_skips_prefill_when_no_similar(monkeypatch):
    """无相似历史时不二次调用 form_task（避免无谓的 LLM 调用）。
    With no similar history, form_task is not called a second time."""
    from core.orchestrator import pipeline as pl
    from core.orchestrator.control import StopController
    from core.orchestrator.intent import IntentResult
    from core.orchestrator.session import Session
    from core.orchestrator.task import MissingItem, Task

    calls: list = []

    async def fake_form(intent, confirmed=None):
        calls.append(confirmed)
        return Task(id="t1", goal="导出报表", params={}, missing=[MissingItem(question="哪个季度？")], risk="read")

    async def fake_find(goal, **kw):
        return None

    monkeypatch.setattr(pl, "form_task", fake_form)
    monkeypatch.setattr(pl, "find_similar", fake_find)
    monkeypatch.setattr(pl, "judge_intent", _fake_judge)
    monkeypatch.setattr(pl, "run_clarify", _fake_clarify)
    monkeypatch.setattr(pl, "execute_task", _fake_execute)
    monkeypatch.setattr(pl, "extract_and_store", lambda *a, **k: _noop())
    monkeypatch.setattr(pl, "get_facts_store", lambda: object())

    s = Session()
    events: asyncio.Queue = asyncio.Queue()
    await pl.run_pipeline("导出报表", s, events, StopController())
    assert calls == [None], "无相似历史时不应二次调用 form_task"
```

在该文件顶部（`_FakeLLMClient` 之后）加三个小助手：

```python
def _intent_task():
    """构造一个「任务」意图。Build a task intent."""
    from core.orchestrator.intent import IntentResult
    return IntentResult(type="task", summary="做事")


# 注意：流水线里 judge_intent / form_task / execute_task / extract_and_store / run_clarify
# 都是被 await 的，桩必须写成 async def —— 用同步 lambda 会报
# "object dict can't be used in 'await' expression"。
# These are all awaited by the pipeline, so the fakes must be async functions.
async def _fake_judge(text):
    """判定为任务意图。Classify as a task intent."""
    return _intent_task()


async def _fake_execute(*a, **k):
    """返回成功结果。Return a successful result."""
    return _done_result()


async def _fake_clarify(sess, task):
    """澄清无额外产出。Clarification yields nothing."""
    return _empty_params()


def _done_result():
    """构造一个成功结果。Build a successful result."""
    return {"status": "done", "summary": "完成", "steps": []}


async def _noop():
    """空协程。An empty coroutine."""
    return None


def _empty_params():
    """空参数（澄清无额外产出）。Empty params."""
    return {}


def _drain(q: asyncio.Queue) -> list:
    """排空队列。Drain the queue."""
    out = []
    while not q.empty():
        out.append(q.get_nowait())
    return out
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_orchestrator_pipeline.py -q -k prefill`
Expected: FAIL — `AttributeError: module 'core.orchestrator.pipeline' has no attribute 'find_similar'`

- [ ] **Step 3: 实现**

`core/orchestrator/pipeline.py` —— import 段加：

```python
from core.tasks.store import TaskStore

# 任务库存储（懒加载单例，便于测试替换）。
# Task-library store (lazy singleton, easy to swap in tests).
_task_store: TaskStore | None = None


def _get_task_store() -> TaskStore:
    """取任务库存储。Get the task-library store."""
    global _task_store
    if _task_store is None:
        _task_store = TaskStore()
    return _task_store


async def find_similar(goal: str) -> dict | None:
    """查找相似历史任务（无命中返回 None）。Find a similar archived task, or None."""
    return await _get_task_store().find_similar(goal)
```

把澄清段替换为：

```python
    if task.missing:
        # 先用历史成功任务预填：必须以 confirmed **重新** form_task，否则 missing 已算好、
        # 预填不会让它变小（本功能的关键点）。
        # Prefill from a similar archived task first: form_task must be re-run with
        # `confirmed`, because `missing` has already been computed and prefilling alone
        # would not shrink it — this is the crux of the feature.
        hist = await find_similar(task.goal)
        if hist is not None:
            await session.notify(f"参考了历史任务，已预填 {len(hist['params'])} 个参数")
            task = await form_task(intent, confirmed=hist["params"])
            session.task = task
            task.params = {**hist["params"], **task.params}
    if task.missing:
        session.set_state(SessionState.CLARIFYING)
        task.params = await run_clarify(session, task)
```

- [ ] **Step 4: 运行确认通过 + 全量后端回归**

Run: `python -m pytest tests/ -q && python -m mypy core/ server.py`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add core/orchestrator/pipeline.py tests/test_orchestrator_pipeline.py
git commit -m "feat(编排): 澄清前用历史成功任务预填参数

关键点：预填必须以 confirmed **重新** form_task —— 此时 missing 已由首次
form_task 算好，只填 task.params 不会让它变小，功能等于白做。

预填时发 notify 让用户看到（不静默改变行为）。无相似历史时不二次调用
form_task，避免无谓的 LLM 调用。"
```

---

## Task 5: 完成确认 + 存档（mode="task"）

**Files:**
- Modify: `core/orchestrator/pipeline.py`（`run_pipeline` 签名 + `execute_task` 之后）
- Test: `tests/test_orchestrator_pipeline.py`

**Interfaces:**
- Consumes: Task 1 的 `TaskStore.record`；Task 4 的 `_get_task_store`
- Produces: `run_pipeline(..., mode: str = "chat")`；模块级 `COMPLETION_OPTIONS`

- [ ] **Step 1: 写失败测试**

追加：

```python
@pytest.mark.asyncio
async def test_task_mode_asks_completion_and_records_on_yes(monkeypatch):
    """任务模式下完成时发确认提问；答「完成了」才存档。"""
    from core.orchestrator import pipeline as pl
    from core.orchestrator.control import StopController
    from core.orchestrator.session import Answer, Session
    from core.orchestrator.task import Task

    recorded: list = []

    class _Ch:
        def __init__(self):
            self.kinds, self.options, self.notified = [], [], []
        async def ask(self, q, *, kind="text", options=None):
            self.kinds.append(kind); self.options.append(options or []); self.notified.append(q)
            return Answer(choice="yes")
        async def notify(self, text):
            self.notified.append(text)

    class _Store:
        async def record(self, task, result, session_id=""):
            recorded.append((task.goal, session_id))

    monkeypatch.setattr(pl, "_get_task_store", lambda: _Store())
    monkeypatch.setattr(pl, "judge_intent", _fake_judge)
    monkeypatch.setattr(pl, "form_task", _fake_form_plain)
    monkeypatch.setattr(pl, "execute_task", _fake_execute)
    monkeypatch.setattr(pl, "extract_and_store", lambda *a, **k: _noop())
    monkeypatch.setattr(pl, "get_facts_store", lambda: object())

    s = Session()
    ch = _Ch()
    events: asyncio.Queue = asyncio.Queue()
    await pl.run_pipeline("做事", s, events, StopController(), channel=ch, mode="task")

    assert ch.kinds == ["choice"], "完成确认必须是 choice 类"
    assert [o["value"] for o in ch.options[0]] == ["yes", "no"]
    assert recorded == [("做事", s.id)]


@pytest.mark.asyncio
async def test_task_mode_no_record_when_not_completed(monkeypatch):
    """答「没完成」不存档。Answering "not completed" does not archive."""
    from core.orchestrator import pipeline as pl
    from core.orchestrator.control import StopController
    from core.orchestrator.session import Answer, Session

    recorded: list = []

    class _Ch:
        async def ask(self, q, *, kind="text", options=None):
            return Answer(choice="no")
        async def notify(self, text):
            pass

    class _Store:
        async def record(self, task, result, session_id=""):
            recorded.append(task.goal)

    monkeypatch.setattr(pl, "_get_task_store", lambda: _Store())
    monkeypatch.setattr(pl, "judge_intent", _fake_judge)
    monkeypatch.setattr(pl, "form_task", _fake_form_plain)
    monkeypatch.setattr(pl, "execute_task", _fake_execute)
    monkeypatch.setattr(pl, "extract_and_store", lambda *a, **k: _noop())
    monkeypatch.setattr(pl, "get_facts_store", lambda: object())

    s = Session()
    events: asyncio.Queue = asyncio.Queue()
    await pl.run_pipeline("做事", s, events, StopController(), channel=_Ch(), mode="task")
    assert recorded == []


@pytest.mark.asyncio
async def test_chat_mode_never_asks_completion(monkeypatch):
    """对话模式（缺省）完全不问、不存档 —— 向后兼容回归。"""
    from core.orchestrator import pipeline as pl
    from core.orchestrator.control import StopController
    from core.orchestrator.session import Answer, Session

    asked: list = []

    class _Ch:
        async def ask(self, q, *, kind="text", options=None):
            asked.append(q)
            return Answer(choice="yes")
        async def notify(self, text):
            pass

    monkeypatch.setattr(pl, "judge_intent", _fake_judge)
    monkeypatch.setattr(pl, "form_task", _fake_form_plain)
    monkeypatch.setattr(pl, "execute_task", _fake_execute)
    monkeypatch.setattr(pl, "extract_and_store", lambda *a, **k: _noop())
    monkeypatch.setattr(pl, "get_facts_store", lambda: object())

    s = Session()
    events: asyncio.Queue = asyncio.Queue()
    await pl.run_pipeline("做事", s, events, StopController(), channel=_Ch())   # 缺省 mode
    assert asked == [], "对话模式不应发完成确认"
```

再加一个 `_task_without_missing` 助手：

```python
def _task_without_missing():
    """构造一个无缺失信息的任务。Build a task with nothing missing."""
    from core.orchestrator.task import Task
    return Task(id="t1", goal="做事", params={}, missing=[], risk="read")


async def _fake_form_plain(intent, confirmed=None):
    """不产生缺失信息的 form_task 桩（必须 async —— 流水线会 await 它）。"""
    return _task_without_missing()
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_orchestrator_pipeline.py -q -k "completion or chat_mode"`
Expected: FAIL — `TypeError: run_pipeline() got an unexpected keyword argument 'mode'`

- [ ] **Step 3: 实现**

`core/orchestrator/pipeline.py` —— 在 `_spawn_bg` 附近加常量：

```python
# 完成确认的两个固定选项（任务模式用）。
# The two fixed options of the completion confirmation (task mode).
COMPLETION_OPTIONS = [
    {"value": "yes", "label": "完成了"},
    {"value": "no", "label": "没完成"},
]
```

`run_pipeline` 签名加 `mode`：

```python
async def run_pipeline(text: str, session: Session, events: asyncio.Queue,
                       controller: StopController, channel: OperatorChannel | None = None,
                       messages: list[dict] | None = None, mode: str = "chat") -> None:
```

在 `result = await execute_task(...)` 之后、`session.set_state(SessionState.REPORTING)` 之前插入：

```python
    # 任务模式：完成后询问「完成了吗」，答「完成了」才存档（需求：只记录成功的任务）。
    # Task mode: ask whether the task is done and archive only on "completed" — the
    # requirement is to record successful tasks only.
    if mode == "task" and result.get("status") == "done":
        answer = await session.ask("这个任务完成了吗？", kind="choice", options=COMPLETION_OPTIONS)
        if answer.choice == "yes":
            try:
                await _get_task_store().record(task, result, session_id=session.id)
            except Exception as e:
                logger.warning("任务存档失败: {}", e)   # 存档失败不该影响汇报
```

在 `pipeline.py` 顶部确保导入 logger：`from core.logger import logger`（若无则加）。

- [ ] **Step 4: 运行确认通过 + 全量后端回归**

Run: `python -m pytest tests/ -q && python -m mypy core/ server.py`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add core/orchestrator/pipeline.py tests/test_orchestrator_pipeline.py
git commit -m "feat(编排): 任务模式下完成时询问并存档成功任务

复用 P4 的 kind=choice 机制，不新增询问类型。只对 status=done 询问；
答「没完成」不记录（需求只要求记录成功的任务）。对话模式（缺省）完全
不问 —— 向后兼容。存档失败只记 warning，不影响汇报。"
```

---

## Task 6: `/voice/utter` 接收 `mode`

**Files:**
- Modify: `core/api/voice.py`（`voice_utter` 的 params 解析与 `run_pipeline` 调用）
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: Task 5 的 `run_pipeline(..., mode=...)`
- Produces: `/voice/utter` 请求体接受 `mode`（缺省 `"chat"`；非法值也按 `"chat"`）

- [ ] **Step 1: 写失败测试**

在 `tests/test_server.py` 追加：

```python
def test_voice_utter_passes_mode_to_pipeline(client, monkeypatch):
    """mode 从请求体传到 pipeline；非法/缺失一律按 chat。"""
    from core.orchestrator import pipeline as pl
    captured = {}

    def fake_run_pipeline(text, session, events, controller, channel=None, messages=None, mode="chat"):
        captured["mode"] = mode
        async def _gen():
            return
            yield
        return _gen()

    monkeypatch.setattr(pl, "run_pipeline", fake_run_pipeline)
    import core.api.voice as voice_mod
    monkeypatch.setattr(voice_mod, "run_pipeline", fake_run_pipeline, raising=False)

    with client.stream("POST", "/api/voice/utter", json={"text": "做事", "mode": "task"}) as r:
        assert r.status_code == 200
        list(r.iter_lines())
    assert captured["mode"] == "task"

    with client.stream("POST", "/api/voice/utter", json={"text": "做事", "mode": "胡说"}) as r:
        list(r.iter_lines())
    assert captured["mode"] == "chat", "非法 mode 回退 chat"

    with client.stream("POST", "/api/voice/utter", json={"text": "做事"}) as r:
        list(r.iter_lines())
    assert captured["mode"] == "chat", "缺省 chat（向后兼容）"
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_server.py -q -k passes_mode`
Expected: FAIL — `KeyError: 'mode'`（`fake_run_pipeline` 未被以 mode 调用）

- [ ] **Step 3: 实现**

`core/api/voice.py` 的 `voice_utter` —— 在 `messages` 解析之后加：

```python
    # 模式：task = 完成后询问并存档；其余（含缺失/非法）一律 chat（向后兼容）。
    # Mode: "task" asks and archives on completion; anything else (missing or invalid) is
    # "chat" for backward compatibility.
    mode = "task" if params.get("mode") == "task" else "chat"
```

并把 `run_pipeline(...)` 调用改为：

```python
    runner = asyncio.ensure_future(
        run_pipeline(text, session, events, controller, messages=messages, mode=mode))
```

- [ ] **Step 4: 运行确认通过 + 全量后端回归**

Run: `python -m pytest tests/ -q && python -m mypy core/ server.py`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add core/api/voice.py tests/test_server.py
git commit -m "feat(API): /voice/utter 接收 mode（缺省 chat，非法值回退 chat）

请求体手工解析，无需改 schema。缺省 chat 保证老前端行为完全不变。"
```

---

## Task 7: 前端模式开关

**Files:**
- Modify: `web/src/composables/assistant/store.ts`（`assistantMode` 单例 + localStorage）
- Modify: `web/src/components/layout/AppHeader.vue`（`[对话][任务]` 开关）
- Modify: `web/src/api.ts`（`streamUtter` 请求体带 `mode`）
- Modify: `web/src/composables/assistant/useChat.ts`（`runTurn` 传 `mode`）
- Test: `web/src/composables/assistant/__tests__/assistantMode.spec.ts`（新建）

**Interfaces:**
- Consumes: 无
- Produces: `assistantMode: Ref<'chat' | 'task'>`（`store.ts` 导出）；`setAssistantMode(m)`；`api.streamUtter(text, handlers, opts)` 的 `opts.mode`

- [ ] **Step 1: 写失败测试**

新建 `web/src/composables/assistant/__tests__/assistantMode.spec.ts`：

```ts
import { beforeEach, describe, expect, it } from 'vitest'
import { assistantMode, setAssistantMode } from '../store'

/** 助手模式：显式切换 + localStorage 持久化。
 *  Assistant mode: explicit switching with localStorage persistence. */
describe('assistantMode', () => {
  beforeEach(() => {
    localStorage.clear()
    assistantMode.value = 'chat'
  })

  /** 缺省为对话模式（不询问完成、不改行为）。Defaults to chat mode. */
  it('缺省为 chat', () => {
    expect(assistantMode.value).toBe('chat')
  })

  /** 切换写回 localStorage。Switching persists to localStorage. */
  it('切换持久化', () => {
    setAssistantMode('task')
    expect(assistantMode.value).toBe('task')
    expect(localStorage.getItem('xluo.assistantMode')).toBe('task')
  })

  /** 非法持久化值回退 chat（防止手改 localStorage 造成未知模式）。 */
  it('非法持久化值回退 chat', async () => {
    localStorage.setItem('xluo.assistantMode', '胡说')
    const { loadStoredMode } = await import('../store')
    expect(loadStoredMode()).toBe('chat')
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd web && npx vitest run src/composables/assistant/__tests__/assistantMode.spec.ts`
Expected: FAIL — `assistantMode` 未导出

- [ ] **Step 3: 实现**

`web/src/composables/assistant/store.ts` —— 加：

```ts
/** 助手模式：对话 = 少打断、完成不询问；任务 = 完成后询问并存档。
 *  Assistant mode: chat stays out of the way and never asks on completion; task asks and
 *  archives on completion. */
export type AssistantMode = 'chat' | 'task'

const MODE_KEY = 'xluo.assistantMode'

/**
 * 读取持久化的模式；非法值回退 chat。
 * Read the persisted mode, falling back to chat for an invalid value.
 *
 * @returns 助手模式。The assistant mode.
 */
export function loadStoredMode(): AssistantMode {
  try {
    return localStorage.getItem(MODE_KEY) === 'task' ? 'task' : 'chat'
  } catch { return 'chat' }
}

/** 当前助手模式（模块级单例，与 assistant 其余状态同模式）。Current assistant mode. */
export const assistantMode = ref<AssistantMode>(loadStoredMode())

/**
 * 切换助手模式并持久化。
 * Switch the assistant mode and persist it.
 *
 * @param m 目标模式。The target mode.
 */
export function setAssistantMode(m: AssistantMode) {
  assistantMode.value = m
  try { localStorage.setItem(MODE_KEY, m) } catch { /* 隐私模式忽略 */ }
}
```

`web/src/components/layout/AppHeader.vue` —— 在 `ah-nav` 之后加开关：

```vue
    <!-- 助手模式开关：对话 = 少打断；任务 = 完成后询问并存档。
         Assistant mode switch: chat stays out of the way; task asks and archives on completion. -->
    <div class="ah-mode">
      <button
        class="ah-mode-item"
        :class="{ on: assistantMode === 'chat' }"
        type="button"
        @click="setAssistantMode('chat')"
      >对话</button>
      <button
        class="ah-mode-item"
        :class="{ on: assistantMode === 'task' }"
        type="button"
        @click="setAssistantMode('task')"
      >任务</button>
    </div>
```

script 里加：

```ts
import { assistantMode, setAssistantMode } from '../../composables/assistant/store'
```

样式加：

```css
.ah-mode { margin-left: auto; display: flex; gap: 2px; background: var(--surface-control); border-radius: var(--r-full); padding: 2px; }
.ah-mode-item { font-size: var(--fs-2xs); color: var(--text-3); background: none; border: none; border-radius: var(--r-full); padding: 3px 10px; cursor: pointer; }
.ah-mode-item.on { color: var(--brand-c2); background: rgba(11, 17, 32, .75); }
```

`web/src/api.ts` —— `streamUtter` 的 opts 加 `mode`，并放进请求体：

```ts
  opts?: { signal?: AbortSignal; sessionId?: string; messages?: unknown[]; mode?: string }
```
```ts
      body: JSON.stringify({
        text,
        session_id: opts?.sessionId || undefined,
        messages: opts?.messages,
        mode: opts?.mode,
      }),
```

`web/src/composables/assistant/useChat.ts` —— `runTurn` 的调用处带上当前模式：

```ts
  }, { messages: history, sessionId: currentSessionId.value || undefined,
       signal: abortController.signal, mode: assistantMode.value })
```
并在 import 行加入 `assistantMode`。

- [ ] **Step 4: 运行确认通过 + 全量前端回归**

Run: `cd web && npm test && npm run build`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add web/src/composables/assistant/store.ts web/src/components/layout/AppHeader.vue web/src/api.ts web/src/composables/assistant/useChat.ts web/src/composables/assistant/__tests__/assistantMode.spec.ts
git commit -m "feat(web): [对话][任务] 模式开关（localStorage 持久化）

模式随 /voice/utter 请求体传给后端；缺省 chat 保证行为不变。
非法持久化值回退 chat。开关放在跨路由的全局头部，用户随时可见自己在哪种模式。"
```

---

## Task 8: 任务库视图

**Files:**
- Create: `web/src/components/console/ConsoleLibrary.vue`
- Modify: `web/src/composables/useConsole.ts`（`CONSOLE_TABS` 加「任务库」）
- Modify: `web/src/views/ConsolePage.vue`（挂载）
- Modify: `web/src/api.ts`（`listLibrary` / `getLibraryTask` / `deleteLibraryTask`）
- Test: `web/src/components/console/__tests__/ConsoleLibrary.spec.ts`（新建）

**Interfaces:**
- Consumes: Task 3 的端点与生成的类型
- Produces: 组件 `ConsoleLibrary`

- [ ] **Step 1: 写失败测试**

新建 `web/src/components/console/__tests__/ConsoleLibrary.spec.ts`：

```ts
// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

vi.mock('../../../api', () => ({
  api: { listLibrary: vi.fn(), getLibraryTask: vi.fn(), deleteLibraryTask: vi.fn() },
}))

import { api } from '../../../api'
import { notify } from '../../../composables/useToast'
import ConsoleLibrary from '../ConsoleLibrary.vue'

const TASKS = {
  ok: true,
  tasks: [
    { id: 1, goal: '复制文件到下载', params: { dest: '下载' }, steps: [{ tool: 'write_file', args: {}, status: 'ok' }],
      status: 'done', created: '2026-09-13T10:00:00', session_id: 's1' },
  ],
}

/** 任务库：列出存档 / 展开看 params 与 steps（只读）/ 删除。 */
describe('ConsoleLibrary', () => {
  beforeEach(() => {
    vi.mocked(api.listLibrary).mockReset()
    vi.mocked(api.listLibrary).mockResolvedValue(TASKS as any)
    vi.mocked(api.deleteLibraryTask).mockReset()
    vi.mocked(api.deleteLibraryTask).mockResolvedValue({ ok: true } as any)
    vi.restoreAllMocks()
  })

  /** 加载成功渲染任务目标。Loads and renders the archived goal. */
  it('加载成功渲染任务', async () => {
    const w = mount(ConsoleLibrary)
    await flushPromises()
    expect(w.text()).toContain('复制文件到下载')
  })

  /** 加载失败展示错误提示（走统一错误处理）。A load failure surfaces the unified error note. */
  it('加载失败展示错误提示', async () => {
    vi.mocked(api.listLibrary).mockRejectedValue(new Error('库文件损坏'))
    const w = mount(ConsoleLibrary)
    await flushPromises()
    expect(w.find('.ui-errnote').text()).toBe('库文件损坏')
  })

  /** 删除失败弹出错误通知。A delete failure emits an error notice. */
  it('删除失败弹出错误通知', async () => {
    vi.mocked(api.deleteLibraryTask).mockRejectedValue(new Error('任务不存在'))
    const errSpy = vi.spyOn(notify, 'err')
    const w = mount(ConsoleLibrary)
    await flushPromises()
    await w.findAll('button').find((b) => b.text() === '删除')!.trigger('click')
    await flushPromises()
    expect(errSpy).toHaveBeenCalledWith('删除任务失败：任务不存在')
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd web && npx vitest run src/components/console/__tests__/ConsoleLibrary.spec.ts`
Expected: FAIL — `Failed to resolve import "../ConsoleLibrary.vue"`

- [ ] **Step 3: 实现**

`web/src/api.ts` 加三个方法（放在 memory 相关端点之后）：

```ts
  /** 任务库：列出存档的成功任务。Task library: list archived successful tasks. */
  listLibrary: () => get<{ ok: boolean; tasks: LibraryTask[] }>('/library'),
  /** 任务库：取单条详情。Task library: fetch one archived task. */
  getLibraryTask: (id: number) => get<{ ok: boolean; task: LibraryTask }>(`/library/${id}`),
  /** 任务库：删除一条。Task library: delete one archived task. */
  deleteLibraryTask: (id: number) => del<ApiResponse>(`/library/${id}`),
```

类型取自已生成的 openapi：在 `web/src/types.ts` 加

```ts
export type LibraryTask = components['schemas']['TaskLibraryItem']
```

新建 `web/src/components/console/ConsoleLibrary.vue`：

```vue
<template>
  <div class="console-library">
    <!-- 任务库头部：说明与刷新。Task-library header: description and refresh. -->
    <div class="lib-head">
      <UiButton variant="ghost" size="sm" @click="loadTasks">刷新</UiButton>
      <span v-if="loading" class="lib-loading">加载中…</span>
    </div>
    <UiErrorNote v-if="error" :error="error" />
    <div v-else-if="!(tasks ?? []).length && !loading" class="console-empty">
      暂无任务存档（任务模式下完成一个任务并确认「完成了」后会出现在这里）
    </div>
    <!-- 任务列表：展开可看参数与步骤（只读）。Task list: expand to view params and steps (read-only). -->
    <UiCard v-for="t in (tasks ?? [])" :key="t.id" class="lib-item">
      <div class="lib-row" @click="toggle(t.id)">
        <span class="lib-goal">{{ t.goal }}</span>
        <span class="lib-time">{{ fmt(t.created) }}</span>
        <span class="lib-count">{{ Object.keys(t.params || {}).length }} 个参数</span>
        <UiButton variant="ghost" size="sm" hover="danger" @click.stop="remove(t.id)">删除</UiButton>
      </div>
      <div v-if="open === t.id" class="lib-detail">
        <div class="lib-sec-title">参数</div>
        <pre>{{ JSON.stringify(t.params, null, 2) }}</pre>
        <div class="lib-sec-title">步骤（只读，不支持回放）</div>
        <pre>{{ JSON.stringify(t.steps, null, 2) }}</pre>
      </div>
    </UiCard>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../../api'
import { useAsync } from '../../composables/useAsync'
import { notify } from '../../composables/useToast'
import { formatError } from '../../errors'
import { UiButton, UiCard, UiErrorNote } from '../ui'

/** 任务库存档加载：统一错误捕获。
 *  Task-library loading with unified error capture. */
const { data: tasks, error, loading, run: loadTasks } = useAsync(async () => {
  const r = await api.listLibrary()
  return r.tasks || []
})

/** 当前展开的任务 id。Currently expanded task id. */
const open = ref<number | null>(null)

/**
 * 展开 / 收起某条任务的详情。
 * Expand / collapse one task's details.
 *
 * @param id 任务 id。The task id.
 */
function toggle(id: number) {
  open.value = open.value === id ? null : id
}

/**
 * 删除一条任务存档并刷新。
 * Delete one archived task and refresh the list.
 *
 * @param id 任务 id。The task id.
 */
async function remove(id: number) {
  try {
    await api.deleteLibraryTask(id)
    notify.ok('已删除任务存档')
    await loadTasks()
  } catch (e) {
    notify.err('删除任务失败：' + formatError(e))
  }
}

/**
 * 格式化时间戳。Format a timestamp.
 *
 * @param ts ISO 时间戳。The ISO timestamp.
 * @returns "YYYY-MM-DD HH:mm"。The formatted timestamp.
 */
function fmt(ts: string) {
  return ts ? ts.replace('T', ' ').slice(0, 16) : ''
}

onMounted(() => { loadTasks() })
</script>

<style scoped>
.console-library { max-width: 720px; width: 100%; margin: 0 auto; display: flex; flex-direction: column; gap: 10px; flex: 1; min-height: 0; overflow-y: auto; }
.lib-head { display: flex; align-items: center; gap: 10px; }
.lib-loading { font-size: 12px; color: var(--text-3); }
.console-empty { display: flex; justify-content: center; color: var(--text-3); font-size: 13px; padding: 40px 0; }
.lib-item { padding: 12px 14px; display: flex; flex-direction: column; gap: 6px; }
.lib-row { display: flex; align-items: center; gap: 10px; cursor: pointer; font-size: 12px; color: var(--text-3); }
.lib-goal { font-size: 14px; font-weight: 600; color: var(--text-1); flex: 1; }
.lib-time { white-space: nowrap; }
.lib-detail { display: flex; flex-direction: column; gap: 4px; border-top: 1px dashed var(--border-soft); padding-top: 8px; }
.lib-sec-title { font-size: var(--fs-2xs); color: var(--text-3); }
.lib-detail pre { margin: 0 0 6px; background: var(--surface-input); border: 1px solid var(--border-base); border-radius: 8px; padding: 8px 10px; font-size: 11px; line-height: 1.6; color: var(--text-2); overflow-x: auto; max-height: 220px; overflow-y: auto; }
</style>
```

`web/src/composables/useConsole.ts` 的 `CONSOLE_TABS` 加一项（放「历史」之后）：

```ts
  { key: 'library', label: '任务库', icon: 'library' },
```

并把 `ConsoleTabKey` 联合类型加上 `'library'`。

`web/src/views/ConsolePage.vue` —— 该文件**只有「对话」tab 是静态 import，其余 tab 一律 `defineAsyncComponent`**（减小初始包）。照此加：

script 里（放在其它 `defineAsyncComponent` 之间）：

```ts
/** 异步加载任务库视图组件 / Async load task-library view component */
const ConsoleLibrary = defineAsyncComponent(() => import('../components/console/ConsoleLibrary.vue'))
```

模板的 `v-if/v-else-if` 链里，插在「历史」与「调度」之间（`ConsoleScheduleView` 是 `v-else` 兜底，**不能插在它之后**）：

```vue
    <!-- 任务库标签页 / Task-library tab -->
    <ConsoleLibrary v-else-if="activeTab === 'library'" />
    <!-- 调度标签页（默认） / Schedule tab (default) -->
    <ConsoleScheduleView v-else />
```

- [ ] **Step 4: 运行确认通过 + 全量前端回归**

Run: `cd web && npm test && npm run build`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add web/src/components/console/ConsoleLibrary.vue web/src/components/console/__tests__/ConsoleLibrary.spec.ts web/src/composables/useConsole.ts web/src/views/ConsolePage.vue web/src/api.ts web/src/types.ts
git commit -m "feat(web): 任务库视图（列出/展开看参数与步骤/删除）

steps 只读展示，不支持回放（回放涉及安全与时效性，是独立议题）。
加载失败走统一错误处理（P4 的 useAsync + UiErrorNote）。"
```

---

## Task 9: 全量验证与端到端

**Files:**
- Modify: `README.md`、`docs/architecture/roadmap.md`

- [ ] **Step 1: 全量自动化**

Run: `python -m pytest tests/ -q && python -m mypy core/ server.py && cd web && npm test && npm run build`
Expected: 全部通过

- [ ] **Step 2: 类型同步门禁**

Run:
```bash
cd web && PYTHONIOENCODING=utf-8 python ../scripts/gen_openapi.py && npx --yes openapi-typescript@7.13.0 src/api/openapi.json -o src/api/generated.ts
git diff --exit-code src/api/generated.ts && echo "OK: 已同步"
```

- [ ] **Step 3: 起服务（严格确认端口）**

```bash
taskkill //F //FI "IMAGENAME eq python.exe" ; sleep 2
netstat -ano | grep ":8520.*LISTENING" || echo "端口空闲"
python main.py serve > /tmp/server.log 2>&1 &
sleep 7 && (grep -qa "10048" /tmp/server.log && echo "❌ 跑的是旧进程" || echo "✓ 绑定成功")
```

- [ ] **Step 4: 端到端验证（可自动化部分）**

1. **模式开关**：`/console` 页面头部有 `[对话][任务]` 开关，点击切换后刷新页面仍是所选模式（localStorage 持久化）
2. **任务库空态**：控制台「任务库」tab 显示空态文案
3. **手工造一条存档**：用 API 直接调 `POST` 不行（无该端点），改为直接向 `memory/tasks.sqlite` 插入一条（或跑一次任务模式对话） → 刷新任务库应能看到，展开显示 params/steps，删除后消失
4. **对话模式回归**：缺省模式下跑一次任务，**不应出现**「这个任务完成了吗？」提问

- [ ] **Step 5: 人工验证（需真实 LLM 与交互，如实记录）**

5. **任务模式完整链路**：切到任务模式 → 发一个会触发澄清的任务 → 观察是否出现「参考了历史任务，已预填 N 个参数」→ 执行完成后出现「这个任务完成了吗？」→ 点「完成了」→ 任务库出现该条
6. **第二次同任务少问**：再发一次同样的任务 → 因命中历史，澄清问题应减少

> 若不具备条件（如 LLM 不可用），**如实标注「未验证」**，不得写成通过。

- [ ] **Step 6: 同步文档**

`README.md`：功能表补「任务知识库」一行；「语音助手使用」附近补模式开关与完成确认的说明。
`docs/architecture/roadmap.md`：P7 状态改为 ✅。

- [ ] **Step 7: 提交并推送**

```bash
git add README.md docs/architecture/roadmap.md
git commit -m "docs: 任务知识库说明与 P7 阶段状态"
git push origin main
```

---

## 完成标准

- [ ] `python -m pytest tests/ -q` 全绿；`python -m mypy core/ server.py` 无问题
- [ ] `cd web && npm test` 全绿；`npm run build` 通过
- [ ] `generated.ts` 与后端 schema 同步（`git diff --exit-code` 无输出）
- [ ] **`find_similar` 的低于阈值 → None 用例全绿**（不误预填的闸门未被放宽）
- [ ] **`_truncate_args` 的长字符串截断用例全绿**（隐私处置生效）
- [ ] `mode` 缺省 `chat` 的向后兼容用例全绿（老前端行为不变）
- [ ] 端到端 4 项自动化验证通过；2 项需真实 LLM 的人工验证**如实记录**（未具备则标「未验证」）
