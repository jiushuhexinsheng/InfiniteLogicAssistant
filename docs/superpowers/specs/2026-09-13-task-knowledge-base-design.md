# 任务知识库 设计文档（P7 / 子系统 E）

日期：2026-09-13
状态：待实施
上游：[Agent 能力扩展路线图](2026-09-13-agent-capabilities-roadmap-design.md) 的子系统 E

## 背景

需求原文：
> 7. 当执行完成任务时要询问是否完成任务，并将成功的任务记录进单独的任务模块，以便今后执行相同或者类似的任务作为参考减少询问

用户已裁决（2026-09-13）：**任务模式要询问、正常模式减少询问** —— 两者不是目标冲突，而是模式差异。

本设计先把路线图标注的阻塞项定下来：**「任务模式 / 正常模式」的判定依据**。在确认前不得假设任何一种。

## 已确认决策

| # | 决策 | 说明 |
|---|---|---|
| 1 | **模式由用户显式切换** | 界面上一个 `[对话] [任务]` 开关。理由：两种模式**行为不同**（问 vs 不问），用户必须能预期「何时会被问」；隐式判定会让人搞不清当前模式 |
| 2 | **连 `steps` 一起存** | 记录工具调用序列（purpose 见决策 3） |
| 3 | **`steps` 的当前用途 = 任务库只读展示** | 不做消费就是死数据（违反 YAGNI）。在任务库界面展示当时做了什么，供用户判断是否复用/删除。**不做回放**（回放涉及安全与时效性，是独立议题） |
| 4 | **`steps` 里的长字符串参数截断** | 工具参数含 `write_file(content=...)`、`run_shell_tool(command=...)`；不截断会把**当时的文件内容**整份留在库里。单个字符串值超 200 字符则截断并标记 |

## 模式开关

`AppHeader.vue`（跨路由的全局头部）的导航区加一个 `[对话] [任务]` 开关。模式是**全局状态**（模块级 ref + localStorage 持久化，与 `ttsSettings` 同模式）。

模式**随 `/voice/utter` 请求体传给后端**（该端点手工解析 JSON body，无需改 schema）：

```json
{ "text": "...", "session_id": "...", "mode": "chat" | "task" }
```

缺省 `"chat"`（向后兼容：老前端不带该字段时行为不变 —— 即「不询问完成」）。

## 完成确认

任务模式下，`execute_task` 返回 `done` 后、汇报前，插一次确认：

```python
if mode == "task" and result.get("status") == "done":
    answer = await session.ask("这个任务完成了吗？", kind="choice", options=COMPLETION_OPTIONS)
    if answer.choice == "yes":
        await record(task, result, session_id=session.id)
```

`COMPLETION_OPTIONS = [{"value":"yes","label":"完成了"}, {"value":"no","label":"没完成"}]`

**复用 P4 的 `kind="choice"` 机制，不新增询问类型。** 答「没完成」则不记录（不追问原因 —— YAGNI）。

失败/停止的任务不询问、不记录（需求原文只要求记录**成功**的任务）。

## 减少询问的机制

**关键点：预填必须发生在 `missing` 产生之前** —— 否则 `missing` 已经算好，预填不会让它变小。

现状（`pipeline.py`）：
```python
task = await form_task(intent)          # ← missing 在此产生
if task.missing:
    task.params = await run_clarify(session, task)
```

改为：
```python
task = await form_task(intent)
if task.missing:
    hist = await find_similar(task.goal)      # ← 新钩子
    if hist is not None:
        await session.notify(f"参考了历史任务，已预填 {len(hist.params)} 个参数")
        # 用历史参数作为 confirmed 重新形成 → missing 应随之变小
        task = await form_task(intent, confirmed=hist.params)
        task.params = {**hist.params, **task.params}
if task.missing:
    task.params = await run_clarify(session, task)
```

复用既有的 `form_task(intent, confirmed=...)`（澄清循环本来就在用，`task.py:54`）✓

**透明性**：预填时发一条 `notify` 让用户看到，不静默改变行为。

## 存储

新增 `core/tasks/store.py` + `memory/tasks.sqlite`（**普通表，不用 FTS5**）：

```sql
CREATE TABLE tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    goal        TEXT NOT NULL,
    params_json TEXT NOT NULL,
    steps_json  TEXT NOT NULL,
    status      TEXT NOT NULL,
    created     TEXT NOT NULL,
    session_id  TEXT
);
CREATE INDEX idx_tasks_created ON tasks(created DESC);
```

**为什么不用 FTS5**（偏离路线图的初始设想，理由如下）：任务库是**个人任务历史**，规模是几百条量级，全表扫描的代价可忽略。而 FTS5 会引入虚拟表 + 三个同步触发器，以及一个更棘手的问题 —— **bm25 的分数量纲依赖数据规模，拿它当「够不够相似」的阈值本身就是个坑**。

改为**纯 Python 的字符 trigram Jaccard 相似度**，阈值明确、与数据规模无关、且可穷尽测试：

```python
_SIMILARITY_THRESHOLD = 0.5

def _trigrams(s: str) -> set[str]:
    """字符级三元组。Character-level trigrams."""
    s = "".join(s.split())
    return {s[i:i+3] for i in range(len(s) - 2)} if len(s) >= 3 else {s}

def similarity(a: str, b: str) -> float:
    """两个字符串的 trigram Jaccard 相似度（0..1）。

    Trigram Jaccard similarity between two strings (0..1).
    """
    ta, tb = _trigrams(a), _trigrams(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)
```

若日后库变大到扫描成瓶颈，再加 FTS5 做**候选召回**、仍用 Jaccard 做**判定** —— 判定逻辑不依赖 FTS5 的分数。

接口：

```python
def record(task: Task, result: dict, session_id: str = "") -> None
def find_similar(goal: str, threshold: float = _SIMILARITY_THRESHOLD) -> dict | None
    # 返回 {"id", "goal", "params", "created"} 或 None（最高分低于阈值即 None）
def list_tasks(limit: int = 50) -> list[dict]
def get_task(task_id: int) -> dict | None
def delete_task(task_id: int) -> None
```

全部为**同步**接口（SQLite 本地文件，无 IO 等待）；`pipeline` 里用 `asyncio.to_thread` 包裹以免阻塞事件循环，或直接调用（单条查询微秒级）。**取直接调用**，与 `FactStore` 的既有做法一致。

**与既有四套存储的关系**（路线图要求写明）：

| 存储 | 形状 | 为何不复用 |
|---|---|---|
| `memory/facts.sqlite` | topic 为主键、**覆盖式** upsert | 任务记录是**只增不改**的，覆盖式会丢历史 |
| `rag/index.db` | 每次 `index_sources()` **全量 DELETE 重建** | 运行时记录会被下次建索引抹掉 |
| `data/history.db` | 会话形状 | 与「任务」不是同一实体 |
| `data/tasks/*.json` | 单会话一个文件、无索引 | 无法按 goal 相似度检索 |

## Task 加时间戳

`Task`（`task.py:39-51`）无时间戳字段 → 加 `created: str = ""`（ISO 字符串，`form_task` 里填 `datetime.now().isoformat()`）。落盘与任务库存档都用它。

## 任务库界面

控制台新增「任务库」tab（`CONSOLE_TABS` 加一项 `{ key: 'library', label: '任务库', icon: 'library' }`）：

- 列表：`goal` / `created` / 参数个数
- 展开：`params` 与 `steps` **只读**展示
- 删除单条

## 参数截断

`record()` 写入前遍历 `steps`，对其中 `args` 的**字符串值**超 200 字符者截断并加省略标记：

```python
_MAX_ARG_CHARS = 200

def _truncate_args(args: dict) -> dict:
    """工具参数里的长字符串值截断 —— 避免把当时的文件内容整份留在任务库。
    Truncate long string values in tool args so a whole file's contents do not end up
    persisted in the task library."""
```
非字符串值原样保留（数值/布尔/短字符串不受影响）。`goal` 与 `params` 不截断（它们是复用所需的最小信息，且本就短）。

## 测试策略

**后端（TDD）**
- `tasks/store`：`record` / `list_tasks` / `get_task` / `delete_task` 的 CRUD
- **`similarity`**：完全相同 = 1.0；无交集 = 0.0；含空白差异；短于 3 字符的串（走单元素分支）；空串 = 0.0
- **`find_similar` 阈值**：高于阈值返回最高分那条；**低于阈值返回 None**（这是「不误预填」的闸门，必须有用例）；库为空返回 None
- **`_truncate_args`**：长字符串截断并标记、短字符串不动、非字符串不动 —— 这是隐私处置，必须有对抗用例
- `pipeline` 集成：`mode="task"` 且 `done` → 发 completion choice 提问；答 yes 才 `record`；答 no 不记录；`mode="chat"` 完全不问（回归）
- `find_similar` 预填：命中历史 → `form_task` 被以 `confirmed` 二次调用、`task.params` 含历史参数、发了 notify；
  **未命中则不二次调用 `form_task`**（避免无谓的 LLM 调用）
- `form_task(confirmed=...)` 既有行为不回归

**前端（Vitest）**
- 模式开关：切换写回 store + localStorage；`/voice/utter` 请求体带上 `mode`
- 任务库视图：列表渲染 / 展开显示 params 与 steps / 删除

**全量**：`pytest` + `mypy` + `npm test` + `npm run build`

## 风险

| 风险 | 处置 |
|---|---|
| **预填错误参数导致执行错东西** | 只在高相似度时预填（`find_similar` 返回 None 或低分则不填）；发 notify 让用户看到；**P5 的权限策略仍生效** —— 历史预填不等于免确认，exec 工具照样会问 |
| **历史记录过时** | 任务库可删；预填的是**参数**而非执行路径，`run_clarify` 仍可追加澄清 |
| **存 steps 的隐私面** | 决策 4 的截断；且库在本地 `memory/` 下（已 gitignore），不入仓库 |
| **第五套存储增加认知负担** | 已在上表写明与其余四套的关系与 ID 语义；本设计不合并存储（那是独立议题） |
| 模式开关被误设 | 缺省 `chat`（不询问、不改行为）；开关状态在 UI 上常驻可见 |

## 不做（明确排除）

- **回放历史步骤**（涉及安全与时效性，独立议题）
- 向量检索 / embedding（先用字符 trigram Jaccard，看实际命中率再定是否需要更强的相似度）
- 自动清理过期记录（先手动删）
- 合并既有四套存储
- 对「没完成」追问原因
