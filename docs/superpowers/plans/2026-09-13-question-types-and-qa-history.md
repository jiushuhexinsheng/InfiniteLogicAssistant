# 询问类型扩展 + 问答进聊天记录 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把询问类型从 `clarify | confirm` 泛化为 `choice | text | composite`，并让提问与回答进入聊天记录。

**Architecture:** 后端把 `QuestionEvent.kind` 泛化并携带 `options`，`confirm` 并入 `choice`（两个固定选项）；`Task.missing` 由 `list[str]` 改为结构化 `list[MissingItem]`，带三条容错。前端 `QuestionCard` / `ConsoleTaskView` 按 `kind` 三态渲染；`useChat` 在提问与作答时写入 `messages`。

**Tech Stack:** Python 3.14 / FastAPI / pydantic / pytest / mypy；Vue 3.4 + TypeScript + Vite 5 / vue-tsc / Vitest 4。

**Spec:** `docs/superpowers/specs/2026-09-13-question-types-and-qa-history-design.md`

## Global Constraints

- Python 3.14+；后端沿用 `core/` 结构，**新增/修改的 docstring 必须中英双语**（`1d5e4db` 起的全库要求）。
- 前端注释同样中英双语（含 `<!-- -->` 模板注释与 `/** */` JSDoc）。
- **不改 `Answer` 结构**（已是 `text` + `choice` 两独立字段）。
- **不新增 `ChatMessage.kind`**；问答以角色 + `❓` 前缀区分。
- **`Task` / `missing` 未暴露到 API 或前端类型**（已核实：`api/schemas.py` 无 `Task`，`web/src` 无 `missing` 引用），因此**无需重新生成 `web/src/api/generated.ts`**。
- 后端验证：`python -m pytest tests/ -q` + `python -m mypy core/ server.py`。
- 前端验证：`cd web && npm test` + `cd web && npm run build`。
- TDD：先写失败测试 → 运行确认失败 → 最小实现 → 运行确认通过 → 提交。
- **端到端过渡窗口（重要）**：Task 3 之后后端发 `kind="choice"`，而前端在 Task 7 / Task 8 之前仍判 `kind === "confirm"`，此时**真实 UI 的确认问题会退化为文本输入**。各 Task 自身的测试套件在此期间保持全绿（前端测试直接喂入 kind，不依赖后端），CI 不受影响；**端到端行为统一在 Task 10 验证**。不要在中途用真实 UI 验证确认流程。

---

## 文件结构

| 文件 | 职责 | 动作 |
|---|---|---|
| `core/orchestrator/events.py` | SSE 事件契约；新增 `QuestionOption`，泛化 `QuestionEvent` | Modify |
| `core/orchestrator/session.py` | `OperatorChannel.ask` 增 `kind`/`options` | Modify |
| `core/orchestrator/pipeline.py` | `EventQueueChannel.ask` 透传 | Modify |
| `core/orchestrator/confirm.py` | 发 `kind="choice"` + 确认/取消两选项 | Modify |
| `core/orchestrator/task.py` | 新增 `MissingItem`；`Task.missing` 结构化；`form_task` schema 与三条容错 | Modify |
| `core/orchestrator/clarify.py` | 按 `MissingItem.type` 提问；choice 回填 label | Modify |
| `core/scheduler/runner.py` | `_SilentChannel.ask` 补形参 | Modify |
| `core/api/voice.py` | `/voice/answer` 的 `choice` 放宽为任意非空字符串 | Modify |
| `web/src/types.ts` | `QuestionEvent` 泛化；`choice` 类型放宽 | Modify |
| `web/src/api.ts` | `onQuestion` 签名、`answer` 的 `choice` 放宽 | Modify |
| `web/src/composables/assistant/store.ts` | `PendingQuestion` 增 `options`、`kind` 三值 | Modify |
| `web/src/composables/assistant/useChat.ts` | 透传 options；**D**：问答写入 `messages` | Modify |
| `web/src/components/assistant/QuestionCard.vue` | 三态渲染 | Modify |
| `web/src/components/console/ConsoleTaskView.vue` | 按 `kind` 渲染三态 | Modify |
| `tests/test_orchestrator_events.py` | 事件序列化测试 | Create |

---

## Task 1: `QuestionEvent` 泛化

**Files:**
- Modify: `core/orchestrator/events.py`（`QuestionEvent`，约 87-102 行）
- Test: `tests/test_orchestrator_events.py`（新建）

**Interfaces:**
- Consumes: 无（本任务独立）
- Produces: `QuestionOption(value: str, label: str)`；`QuestionEvent(question, session_id="", kind="text", options=[])`，其中 `kind: Literal["choice","text","composite"]`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_orchestrator_events.py`：

```python
# -*- coding: utf-8 -*-
"""SSE 事件契约（QuestionEvent 泛化）的测试。
Tests for the SSE event contract (the generalized QuestionEvent).
"""
from core.orchestrator.events import QuestionEvent, QuestionOption


def test_question_event_defaults_to_text():
    """缺省 kind 为 text，且不带选项。kind defaults to text with no options."""
    evt = QuestionEvent(question="目标位置？", session_id="s1").emit()
    assert evt == {"type": "question", "question": "目标位置？", "session_id": "s1", "kind": "text", "options": []}


def test_question_event_choice_carries_options():
    """选择类携带选项列表（value 机器可读、label 展示用）。
    A choice question carries its option list (value for machines, label for display)."""
    evt = QuestionEvent(
        question="确认执行吗？",
        session_id="s1",
        kind="choice",
        options=[QuestionOption(value="yes", label="确认"), QuestionOption(value="no", label="取消")],
    ).emit()
    assert evt["kind"] == "choice"
    assert evt["options"] == [{"value": "yes", "label": "确认"}, {"value": "no", "label": "取消"}]


def test_question_event_composite_kind():
    """综合类 kind 为 composite。A composite question uses kind=composite."""
    evt = QuestionEvent(question="选一个并补充说明", kind="composite",
                        options=[QuestionOption(value="a", label="甲")]).emit()
    assert evt["kind"] == "composite"
    assert len(evt["options"]) == 1


def test_question_event_rejects_legacy_kinds():
    """旧的 clarify / confirm 不再是合法 kind（已并入 text / choice）。
    The legacy clarify / confirm kinds are no longer valid (folded into text / choice)."""
    import pytest
    from pydantic import ValidationError
    for legacy in ("clarify", "confirm"):
        with pytest.raises(ValidationError):
            QuestionEvent(question="q", kind=legacy)
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_orchestrator_events.py -q`
Expected: FAIL — `ImportError: cannot import name 'QuestionOption'`

- [ ] **Step 3: 实现**

把 `core/orchestrator/events.py` 中的 `QuestionEvent` 整段替换为：

```python
class QuestionOption(BaseModel):
    """询问选项：value 为机器可读取值，label 为展示文案。

    A question option: value is the machine-readable value, label is the display text.
    """

    value: str
    label: str


class QuestionEvent(_BaseEvent):
    """询问：前端回答走 POST /api/voice/answer。

    kind 决定前端渲染方式：
    - text      自由文本输入
    - choice    按 options 渲染按钮（原先的 confirm 即 choice + 确认/取消两项）
    - composite 按钮 + 输入框，任选其一即可提交

    A question: the frontend answers via POST /api/voice/answer. kind decides how the
    frontend renders it: text (free-form input), choice (buttons from options; the
    former confirm is just choice with confirm/cancel), or composite (buttons plus an
    input, either one suffices to submit).
    """

    type: Literal["question"] = "question"
    question: str
    session_id: str = ""
    kind: Literal["choice", "text", "composite"] = "text"
    options: list[QuestionOption] = []
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_orchestrator_events.py -q`
Expected: PASS（4 个用例）

- [ ] **Step 5: 提交**

```bash
git add core/orchestrator/events.py tests/test_orchestrator_events.py
git commit -m "feat(事件): QuestionEvent 泛化为 choice|text|composite

confirm 并入 choice（确认/取消只是两个固定选项），使任意选项集
（含权限策略的 允许一次/永久允许/拒绝）复用同一套机制。
新增 QuestionOption(value, label)。"
```

---

## Task 2: `ask` 透传 `kind` / `options`

**Files:**
- Modify: `core/orchestrator/session.py`（`OperatorChannel.ask` 协议约 41 行、`Session.ask` 约 110 行）
- Modify: `core/orchestrator/pipeline.py`（`EventQueueChannel.ask` 约 80 行）
- Test: `tests/test_orchestrator_pipeline.py`

**Interfaces:**
- Consumes: Task 1 的 `QuestionEvent(kind=..., options=...)`
- Produces: `OperatorChannel.ask(question: str, *, kind: str = "text", options: list | None = None) -> Answer`；`Session.ask(question, *, kind="text", options=None) -> Answer`

- [ ] **Step 1: 写失败测试**

在 `tests/test_orchestrator_pipeline.py` 中，把现有 `test_channel_ask_blocks_until_answer` 的断言改为新契约，并追加两个用例：

```python
@pytest.mark.asyncio
async def test_channel_ask_blocks_until_answer():
    """ask 阻塞直到收到回答；缺省 kind 为 text。ask blocks until an answer arrives; kind defaults to text."""
    events: asyncio.Queue = asyncio.Queue()
    ch = EventQueueChannel(events, session_id="s1")

    async def do_ask():
        return await ch.ask("问题?")

    t = asyncio.ensure_future(do_ask())
    await asyncio.sleep(0.05)
    evt = await events.get()
    assert evt == {"type": "question", "question": "问题?", "session_id": "s1", "kind": "text", "options": []}
    ch.answer("回答")
    assert await t == Answer(text="回答")


@pytest.mark.asyncio
async def test_channel_ask_choice_carries_options_and_choice():
    """选择类提问带 options，回答带结构化 choice。
    A choice question carries options, and the answer carries the structured choice."""
    events: asyncio.Queue = asyncio.Queue()
    ch = EventQueueChannel(events, session_id="s1")

    async def do_ask():
        return await ch.ask("确认执行吗？", kind="choice",
                            options=[{"value": "yes", "label": "确认"}, {"value": "no", "label": "取消"}])

    t = asyncio.ensure_future(do_ask())
    await asyncio.sleep(0.05)
    evt = await events.get()
    assert evt["kind"] == "choice"
    assert evt["options"] == [{"value": "yes", "label": "确认"}, {"value": "no", "label": "取消"}]
    ch.answer("", choice="yes")
    assert await t == Answer(text="", choice="yes")


@pytest.mark.asyncio
async def test_channel_ask_composite_kind():
    """综合类 kind 透传（前端渲染按钮 + 输入框）。A composite kind is passed through (frontend renders buttons plus an input)."""
    events: asyncio.Queue = asyncio.Queue()
    ch = EventQueueChannel(events, session_id="s1")

    async def do_ask():
        return await ch.ask("选一个并补充", kind="composite", options=[{"value": "a", "label": "甲"}])

    t = asyncio.ensure_future(do_ask())
    await asyncio.sleep(0.05)
    assert (await events.get())["kind"] == "composite"
    ch.answer("补充说明")
    assert await t == Answer(text="补充说明")
```

同时把该文件中 `Answer` 的 import 行确认为：

```python
from core.orchestrator.session import Answer
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_orchestrator_pipeline.py -q`
Expected: FAIL — `TypeError: ask() got an unexpected keyword argument 'kind'`

- [ ] **Step 3: 实现**

`core/orchestrator/session.py` — 协议与 `Session.ask`：

```python
    async def ask(self, question: str, *, kind: str = "text", options: list | None = None) -> Answer: ...

    async def notify(self, text: str) -> None: ...
```

```python
    async def ask(self, question: str, *, kind: str = "text", options: list | None = None) -> Answer:
        """向操作者提问并等待回答；无通道时抛 RuntimeError。

        kind 决定前端渲染方式（text / choice / composite），options 供 choice 与
        composite 使用。

        Ask the operator a question and wait for the answer; raise RuntimeError when
        there is no channel. kind decides how the frontend renders it (text / choice /
        composite); options is used by choice and composite.
        """
        if self.channel is None:
            raise RuntimeError("会话无 OperatorChannel，无法向操作者提问")
        return await self.channel.ask(question, kind=kind, options=options)
```

`core/orchestrator/pipeline.py` — `EventQueueChannel.ask`：

```python
    async def ask(self, question: str, *, kind: str = "text", options: list | None = None) -> Answer:
        """写入 question 事件并阻塞等待操作者回答（串行化，同会话同时最多一个待答问题）。

        kind 与 options 随事件下发，前端据此决定渲染按钮还是输入框。

        Write a question event and block until the operator answers (serialized: at most
        one pending question per session). kind and options travel with the event so the
        frontend can decide between buttons and a text input.
        """
        # 串行化提问：同会话同时最多一个待答问题，避免并发子代理答非所问
        async with self._ask_lock:
            await self.events.put(
                QuestionEvent(question=question, session_id=self.session_id,
                              kind=kind, options=options or []).emit()
            )
            return await self.answers.get()
```

（`answer(text, choice=None)` 保持不变。）

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_orchestrator_pipeline.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add core/orchestrator/session.py core/orchestrator/pipeline.py tests/
git commit -m "feat(编排): ask 透传 kind/options，QuestionEvent 携带选项集"
```

> **实施修正（2026-09-13）**：本 Task 改的是 `OperatorChannel.ask` **协议**，
> 必须**同时**更新全部实现方，否则套件变红。除 `core/` 的两处外，还有 6 个
> 测试替身需补 `options=None` 形参，分布在：
> `tests/test_coordinator.py:62`、`tests/test_orchestrator_confirm.py:22`、
> `tests/test_orchestrator_executor.py:41`、`tests/test_orchestrator_task.py:64`、
> `tests/test_skills_executor.py:59` 与 `:103`。
> 原计划漏了后两个文件（改协议时未清点全部实现方），已在实施中补齐。

---

## Task 3: 确认改发 `kind="choice"`

**Files:**
- Modify: `core/orchestrator/confirm.py`（`_ask_operator`，约 65 行）
- Test: `tests/test_orchestrator_confirm.py`

**Interfaces:**
- Consumes: Task 2 的 `Session.ask(question, *, kind, options)`
- Produces: 确认提问固定为 `kind="choice"` + `options=[{"value":"yes","label":"确认"},{"value":"no","label":"取消"}]`；`CONFIRM_OPTIONS` 常量供测试与其他模块引用

- [ ] **Step 1: 写失败测试**

在 `tests/test_orchestrator_confirm.py` 中，把 `_Channel.ask` 改为记录 `kind`/`options`：

```python
class _Channel:
    """模拟会话通道：返回预设答案（Answer 或字符串）并记录通知、提问类型与选项。
    Simulates a session channel: returns preset answers, recording notifications, question kinds and options.
    """

    def __init__(self, answers):
        self.answers = list(answers)
        self.notified: list[str] = []
        self.kinds: list[str] = []
        self.options: list[list] = []

    async def ask(self, q, *, kind="text", options=None):
        self.kinds.append(kind)
        self.options.append(options or [])
        a = self.answers.pop(0)
        return a if isinstance(a, Answer) else Answer(text=a)

    async def notify(self, text):
        self.notified.append(text)
```

替换 `test_confirm_asks_with_confirm_kind` 为：

```python
@pytest.mark.asyncio
async def test_confirm_asks_as_choice_with_two_options():
    """确认提问必须是 kind="choice" 且恰带「确认 / 取消」两个选项。
    A confirmation question must be kind="choice" with exactly the confirm/cancel options."""
    s = Session()
    s.channel = _Channel([Answer(choice="yes")])
    await confirm_if_needed(Task("t", "删文件", risk="exec"), "删除 x", s)
    assert s.channel.kinds == ["choice"]
    assert s.channel.options[0] == [
        {"value": "yes", "label": "确认"},
        {"value": "no", "label": "取消"},
    ]


@pytest.mark.asyncio
async def test_confirm_tool_asks_as_choice():
    """工具级确认同样是选择类。Tool-level confirmation is a choice question too."""
    s = Session()
    s.channel = _Channel([Answer(choice="no")])
    await confirm_tool(s, "write_file", {"path": "x", "content": "y"})
    assert s.channel.kinds == ["choice"]
    assert [o["value"] for o in s.channel.options[0]] == ["yes", "no"]
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_orchestrator_confirm.py -q`
Expected: FAIL — `assert [] == ['choice']`（现在是 `["confirm"]`）

- [ ] **Step 3: 实现**

在 `core/orchestrator/confirm.py` 的 `_EXACT_NO` 之后加入常量：

```python
# 确认提问的两个固定选项（前端据此渲染按钮）；value 供后端判定，label 供展示与记录。
# The two fixed options of a confirmation question (the frontend renders buttons from
# them); value is for the backend decision, label for display and records.
CONFIRM_OPTIONS = [
    {"value": "yes", "label": "确认"},
    {"value": "no", "label": "取消"},
]
```

并把 `_ask_operator` 中的提问行改为：

```python
    answer = await session.ask(f"确认执行吗？{plan}", kind="choice", options=CONFIRM_OPTIONS)
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_orchestrator_confirm.py -q`
Expected: PASS（含原有 `_resolve_confirm` 的全部回归用例）

- [ ] **Step 5: 提交**

```bash
git add core/orchestrator/confirm.py tests/test_orchestrator_confirm.py
git commit -m "refactor(确认): 确认提问改发 kind=choice + 确认/取消两选项

confirm 不再是一个独立 kind。判定逻辑（_resolve_confirm 读 choice=='yes'）
不变，行为等价，全部回归用例保留。"
```

---

## Task 4: `MissingItem` 结构化 + `clarify` 适配

> **本任务合并了「结构变更」与「唯一消费方的适配」**：`Task.missing` 改成 `MissingItem`
> 后 `clarify.py` 会立刻 `TypeError`，拆成两个 Task 会让中间那个 commit 的测试套件变红。
> 结构变更与其消费方的适配必须原子落地。

**Files:**
- Modify: `core/orchestrator/task.py`（`_FORM_TOOL` 的 `missing` 段约 27-30 行、`Task` 约 39-51 行、`form_task` 解析约 82-88 行）
- Modify: `core/orchestrator/clarify.py`（`run_clarify` 整体替换 + 新增 `_answer_text`）
- Test: `tests/test_orchestrator_task.py`、`tests/test_server.py`

**Interfaces:**
- Consumes: Task 2 的 `Session.ask(question, *, kind, options)`
- Produces: `MissingItem(question: str, type: str = "text", options: list[dict] = [])`；`Task.missing: list[MissingItem]`；`parse_missing(raw) -> list[MissingItem]`；`_answer_text(answer: Answer, item: MissingItem) -> str`

- [ ] **Step 1: 写失败测试**

在 `tests/test_orchestrator_task.py` 追加：

```python
def test_parse_missing_wraps_plain_strings():
    """模型不遵守 schema 时，字符串元素兜底为 text 类。Plain string items fall back to text when the model ignores the schema."""
    from core.orchestrator.task import parse_missing
    items = parse_missing(["目标位置？"])
    assert items[0].question == "目标位置？"
    assert items[0].type == "text"
    assert items[0].options == []


def test_parse_missing_defaults_unknown_type_to_text():
    """type 缺失或非法时降级为 text。A missing or invalid type degrades to text."""
    from core.orchestrator.task import parse_missing
    assert parse_missing([{"question": "a"}])[0].type == "text"
    assert parse_missing([{"question": "b", "type": "nonsense"}])[0].type == "text"


def test_parse_missing_downgrades_optionless_choice_to_text():
    """choice/composite 但没有选项时降级为 text —— 没有选项的选择题无法作答。
    A choice/composite without options degrades to text: a multiple-choice question with no options cannot be answered."""
    from core.orchestrator.task import parse_missing
    for kind in ("choice", "composite"):
        assert parse_missing([{"question": "q", "type": kind, "options": []}])[0].type == "text"


def test_parse_missing_keeps_valid_choice():
    """合法的 choice（带选项）原样保留，选项只取 value/label。A valid choice keeps its options, keeping only value/label."""
    from core.orchestrator.task import parse_missing
    item = parse_missing([{
        "question": "选哪个？", "type": "choice",
        "options": [{"value": "a", "label": "甲", "extra": 1}],
    }])[0]
    assert item.type == "choice"
    assert item.options == [{"value": "a", "label": "甲"}]


def test_parse_missing_skips_empty_question():
    """空问题的条目不生成 MissingItem。Entries with an empty question produce no MissingItem."""
    from core.orchestrator.task import parse_missing
    assert parse_missing([{"question": "   "}, ""]) == []
```

并把现有断言 `assert t.missing == ["复制到哪里？"]` 改为：

```python
    assert [m.question for m in t.missing] == ["复制到哪里？"]
```

并把 `test_run_clarify_asks_operator` 更新为新契约（记录 kind、用 `MissingItem` 构造），同时追加两个澄清用例：

```python
@pytest.mark.asyncio
async def test_run_clarify_asks_operator(monkeypatch):
    """澄清流程向操作者提问并返回补齐的参数。Clarification asks the operator and returns the completed params."""
    from core.orchestrator.task import MissingItem

    class _Channel:
        def __init__(self, answers):
            self.answers = list(answers)
            self.asked: list[str] = []
            self.kinds: list[str] = []

        async def ask(self, q, *, kind="text", options=None):
            self.asked.append(q)
            self.kinds.append(kind)
            a = self.answers.pop(0)
            return a if isinstance(a, Answer) else Answer(text=a)

        async def notify(self, text):
            pass

    script = [
        Task("t", "复制文件", {"src": "桌面readme.txt"}, [MissingItem(question="目标位置？")], "write"),
        Task("t", "复制文件", {"src": "桌面readme.txt", "dest": "下载"}, [], "write"),
    ]
    calls = {"n": 0}

    async def fake_form(intent, confirmed=None):
        t = script[min(calls["n"] + 1, len(script) - 1)]
        calls["n"] += 1
        return t

    monkeypatch.setattr("core.orchestrator.clarify.form_task", fake_form)

    s = Session()
    s.channel = _Channel(["下载"])
    task = script[0]
    params = await run_clarify(s, task)
    assert s.channel.asked == ["目标位置？"]
    assert s.channel.kinds == ["text"]
    assert params == {"src": "桌面readme.txt", "dest": "下载"}


@pytest.mark.asyncio
async def test_run_clarify_choice_answer_backfills_label(monkeypatch):
    """选择类缺失信息按 type 提问，回填 option 的 label（人类可读，供模型理解）。
    A choice-type missing item is asked as a choice question and backfills the option's
    label (human-readable, for the model to understand)."""
    from core.orchestrator.task import MissingItem

    class _Channel:
        def __init__(self):
            self.kinds: list[str] = []
            self.options: list[list] = []

        async def ask(self, q, *, kind="text", options=None):
            self.kinds.append(kind)
            self.options.append(options or [])
            return Answer(choice="dest-download")

        async def notify(self, text):
            pass

    script = [
        Task("t", "复制文件", {}, [MissingItem(
            question="复制到哪里？", type="choice",
            options=[{"value": "dest-download", "label": "下载目录"},
                     {"value": "dest-desktop", "label": "桌面"}],
        )], "write"),
        Task("t", "复制文件", {"dest": "下载目录"}, [], "write"),
    ]
    calls = {"n": 0}
    captured: dict = {}

    async def fake_form(intent, confirmed=None):
        captured["confirmed"] = confirmed
        t = script[min(calls["n"] + 1, len(script) - 1)]
        calls["n"] += 1
        return t

    monkeypatch.setattr("core.orchestrator.clarify.form_task", fake_form)

    s = Session()
    s.channel = _Channel()
    task = script[0]
    await run_clarify(s, task)
    assert s.channel.kinds == ["choice"]
    assert [o["value"] for o in s.channel.options[0]] == ["dest-download", "dest-desktop"]
    # 回填的是 label 而非 value
    assert captured["confirmed"] == {"复制到哪里？": "下载目录"}


@pytest.mark.asyncio
async def test_run_clarify_skips_already_asked_by_question(monkeypatch):
    """已问过的问题（按 question 文本判定）不再追问。Already-asked questions (matched by question text) are not asked again."""
    from core.orchestrator.task import MissingItem

    class _Channel:
        def __init__(self):
            self.asked: list[str] = []

        async def ask(self, q, *, kind="text", options=None):
            self.asked.append(q)
            return Answer(text="下载")

        async def notify(self, text):
            pass

    same = MissingItem(question="目标位置？")
    script = [
        Task("t", "复制文件", {}, [same], "write"),
        Task("t", "复制文件", {"dest": "下载"}, [same], "write"),
    ]
    calls = {"n": 0}

    async def fake_form(intent, confirmed=None):
        t = script[min(calls["n"] + 1, len(script) - 1)]
        calls["n"] += 1
        return t

    monkeypatch.setattr("core.orchestrator.clarify.form_task", fake_form)

    s = Session()
    s.channel = _Channel()
    await run_clarify(s, script[0])
    # 第二次循环看到同一个问题 → 停止追问，不重复提问
    assert s.channel.asked == ["目标位置？"]
```

`tests/test_server.py` 第 224 行与 361 行的 `Task(...)` 构造改为使用 `MissingItem`：

```python
    s.task = Task("t", "算 1+1", {"a": 1}, [MissingItem(question="x")], "read")
```
```python
        return Task("t", "算 1+1", {}, [], "read")
```
（第 361 行是空列表，仅需在该文件顶部加 `from core.orchestrator.task import MissingItem, Task` 的 import。）

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_orchestrator_task.py -q`
Expected: FAIL — `ImportError: cannot import name 'parse_missing'`

- [ ] **Step 3: 实现**

`core/orchestrator/task.py` —— `Task` 之前新增：

```python
@dataclass
class MissingItem:
    """任务缺失信息的一条：问题文本 + 期望的作答方式。

    一条缺失信息由 LLM 产出，并决定前端渲染成输入框还是按钮。
    type 为 "choice"/"composite" 时 options 必须非空，否则无法作答（解析时降级为 text）。

    One piece of missing task information: the question text plus how it should be
    answered. Produced by the LLM and deciding whether the frontend renders an input or
    buttons. When type is "choice"/"composite", options must be non-empty or the question
    is unanswerable (the parser degrades it to text).
    """

    question: str
    type: str = "text"  # text | choice | composite
    options: list[dict] = field(default_factory=list)
```

把 `Task.missing` 的类型改为 `list[MissingItem]`：

```python
    missing: list[MissingItem] = field(default_factory=list)
```

在 `form_task` 之前新增解析函数：

```python
_VALID_TYPES = ("text", "choice", "composite")


def parse_missing(raw: Any) -> list[MissingItem]:
    """把 LLM 产出的 missing 解析为 MissingItem 列表，带三条容错。

    容错（form_task 依赖 LLM 输出，schema 不保证被遵守）：
    1. 元素是字符串 → 当作 text 类问题
    2. type 缺失或非法 → text
    3. type 为 choice/composite 但 options 为空 → 降级为 text（没有选项无法作答）

    Parse the LLM-produced missing list into MissingItems with three fallbacks. form_task
    depends on LLM output and the schema is not guaranteed to be honoured, so: (1) a plain
    string element becomes a text question; (2) a missing or invalid type becomes text;
    (3) a choice/composite with no options degrades to text, since it cannot be answered.

    Args:
        raw: LLM 产出的 missing 原始值。The raw missing value produced by the LLM.

    Returns:
        MissingItem 列表（问题为空的条目被跳过）。The list of MissingItems (entries with an empty question are skipped).
    """
    items: list[MissingItem] = []
    for entry in raw or []:
        if isinstance(entry, str):
            question, kind, options = entry.strip(), "text", []
        elif isinstance(entry, dict):
            question = str(entry.get("question") or "").strip()
            kind = entry.get("type") if entry.get("type") in _VALID_TYPES else "text"
            options = [
                {"value": str(o.get("value", "")), "label": str(o.get("label", ""))}
                for o in (entry.get("options") or [])
                if isinstance(o, dict)
            ]
        else:
            continue
        if not question:
            continue
        if kind in ("choice", "composite") and not options:
            kind = "text"  # 没有选项的选择题无法作答 / an optionless multiple-choice is unanswerable
        items.append(MissingItem(question=question, type=kind, options=options))
    return items
```

把 `_FORM_TOOL` 里 `missing` 的定义替换为：

```python
                "missing": {
                    "type": "array",
                    "description": "需要向操作者确认的缺失信息",
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string", "description": "要问操作者的问题"},
                            "type": {
                                "type": "string",
                                "enum": ["text", "choice", "composite"],
                                "description": "作答方式：text 自由文本 / choice 从选项选 / composite 选项加补充说明",
                            },
                            "options": {
                                "type": "array",
                                "description": "type 为 choice 或 composite 时必填",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "value": {"type": "string"},
                                        "label": {"type": "string"},
                                    },
                                    "required": ["value", "label"],
                                },
                            },
                        },
                        "required": ["question"],
                    },
                },
```

把 `form_task` 中构造 `Task` 的 `missing` 行替换为：

```python
                    missing=parse_missing(data.get("missing")),
```

**同一 Task 内必须适配 `clarify.py`**（否则 `TypeError: 'str' object has no attribute 'question'`，套件变红）。把 `core/orchestrator/clarify.py` 的 `run_clarify` 整个函数体替换为，并在其后新增 `_answer_text`：

```python
async def run_clarify(session: Session, task: Task) -> dict:
    """逐条把 task.missing 问给操作者，用回答重新形成任务，直到 missing 为空或轮次/重复上限。

    每条缺失信息自带作答方式（MissingItem.type/options）：text 走自由文本，
    choice/composite 走结构化选择。选择类回答回填 **option 的 label**（人类可读，
    便于模型理解），value 在选项中找不到时回退为原始值。

    Asks the operator each item in task.missing one by one, re-forming the task with the
    answers until missing is empty or the round/repetition limit is hit. Each missing item
    carries how it should be answered (MissingItem.type/options): text uses free input
    while choice/composite use a structured choice. A choice answer backfills the option's
    **label** (human-readable, for the model to understand), falling back to the raw value
    when it is not among the options.
    """
    asked: set[str] = set()
    answered: dict[str, str] = {}
    for _ in range(MAX_CLARIFY_ROUNDS):
        if not task.missing:
            break
        item = task.missing[0]
        if item.question in asked:
            logger.warning("澄清重复问题，停止追问: {}", item.question)
            break
        asked.add(item.question)
        answer = await session.ask(item.question, kind=item.type, options=item.options)
        text = _answer_text(answer, item)
        if not text:
            break
        answered[item.question] = text
        # 全部已答作为结构化 confirmed 传入重新形成任务（goal 保持干净）
        new_task = await form_task(IntentResult(type="task", summary=task.goal), confirmed=answered)
        task.goal = new_task.goal or task.goal
        # 保留先前已确认参数，新结果覆盖同名键
        task.params = {**task.params, **new_task.params}
        # 过滤已问过的问题（按 question 文本），避免 LLM 重问
        task.missing = [m for m in new_task.missing if m.question not in asked]
    return dict(task.params)


def _answer_text(answer: Answer, item: MissingItem) -> str:
    """把一条回答转成回填给 LLM 的文本。

    选择类取被选 option 的 label；找不到时回退原始 value。文本类取 text。

    Convert an answer into the text backfilled to the LLM. A choice answer takes the
    selected option's label, falling back to the raw value when not found; a text answer
    takes its text.

    Args:
        answer: 操作者回答。The operator's answer.
        item: 对应的缺失信息。The corresponding missing item.

    Returns:
        供回填的文本，可能为空串。The text to backfill, possibly empty.
    """
    if answer.choice is not None:
        for opt in item.options:
            if opt.get("value") == answer.choice:
                return str(opt.get("label") or answer.choice)
        return answer.choice
    return answer.text.strip()
```

并把该文件的 import 行更新为：

```python
from core.orchestrator.session import Answer, Session
from core.orchestrator.task import MissingItem, Task, form_task
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_orchestrator_task.py tests/test_server.py -q`
Expected: PASS

- [ ] **Step 5: 全量后端回归（必须全绿）**

Run: `python -m pytest tests/ -q && python -m mypy core/ server.py`
Expected: 全部通过。若出现 `AttributeError: 'str' object has no attribute 'question'`，说明 `clarify.py` 未适配到位（见 Step 3 后半段）。

- [ ] **Step 6: 提交**

```bash
git add core/orchestrator/task.py core/orchestrator/clarify.py tests/test_orchestrator_task.py tests/test_server.py
git commit -m "feat(任务): missing 结构化为 MissingItem + clarify 按 type 提问

form_task 依赖 LLM 输出，schema 不保证被遵守，故解析容错：字符串元素当作
text；type 缺失/非法降级 text；choice/composite 无选项也降级 text（没有选项
的选择题无法作答）。

clarify 同步适配（结构变更与唯一消费方的适配必须原子落地，否则中间 commit
的套件会红）：按 MissingItem.type 提问，选择类回填 option 的 label 而非
value（人类可读，便于模型理解），去重按 question 文本。"
```

---

## Task 5: `_SilentChannel` 补形参 + `choice` 校验放宽

**Files:**
- Modify: `core/scheduler/runner.py`（`_SilentChannel.ask` 约 31 行）
- Modify: `core/api/voice.py`（`voice_answer`，约 238-246 行）
- Test: `tests/test_scheduler_runner.py`、`tests/test_server.py`

**Interfaces:**
- Consumes: Task 2 的 `ask(question, *, kind, options)`
- Produces: 无新接口；`/api/voice/answer` 接受任意非空 `choice` 字符串

- [ ] **Step 1: 写失败测试**

`tests/test_scheduler_runner.py` —— 把 `test_silent_channel_ask_records_rejected` 改为：

```python
@pytest.mark.asyncio
async def test_silent_channel_ask_records_rejected():
    """测试静默通道在无人应答时记录被拒请求。Tests the silent channel recording rejected asks when no one answers."""
    ch = _SilentChannel()
    ans = await ch.ask("确认执行吗？删除 /tmp/x", kind="choice",
                       options=[{"value": "yes", "label": "确认"}, {"value": "no", "label": "取消"}])
    assert ans == Answer()  # 无人应答 → 无 choice → 确认被拒
    assert ans.choice is None
    assert ch.rejected == ["确认执行吗？删除 /tmp/x"]
```

`tests/test_server.py` —— 在已有的 `test_voice_answer_passes_structured_choice` 之后追加：

```python
def test_voice_answer_accepts_arbitrary_choice(client):
    """choice 不限于 yes/no —— 权限策略的「允许一次 / 永久允许」等取值必须能透传。
    choice is not limited to yes/no: values such as the permission policy's
    allow-once / allow-always must pass through. 取值合法性由消费方自行校验。"""
    import asyncio

    from core.api import state
    from core.orchestrator.control import StopController
    from core.orchestrator.pipeline import EventQueueChannel
    from core.orchestrator.session import Answer, Session

    session = Session(session_id="ans-arb")
    channel = EventQueueChannel(asyncio.Queue(), "ans-arb")
    session.channel = channel
    state.register(session, StopController())
    try:
        r = client.post("/api/voice/answer", json={"session_id": "ans-arb", "text": "", "choice": "always"})
        assert r.status_code == 200
        assert channel.answers.get_nowait() == Answer(text="", choice="always")
    finally:
        state.cleanup("ans-arb")
```

同时把已有的 `test_voice_answer_passes_structured_choice` 中「非法 choice 不透传」那个断言改为「空 choice 视为未选择」：

```python
        # 空字符串 choice 视为未选择（不去猜用户的意图）
        r2 = client.post("/api/voice/answer", json={"session_id": "ans-choice", "text": "随便吧", "choice": ""})
        assert r2.status_code == 200
        assert channel.answers.get_nowait() == Answer(text="随便吧", choice=None)
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_scheduler_runner.py tests/test_server.py -q`
Expected: FAIL — `TypeError: ask() got an unexpected keyword argument 'kind'` 与 `assert Answer(text='', choice=None) == Answer(text='', choice='always')`

- [ ] **Step 3: 实现**

`core/scheduler/runner.py` —— `_SilentChannel.ask`：

```python
    async def ask(self, question: str, *, kind: str = "text", options: list | None = None) -> Answer:
        """向操作者提问：无人值守时记录问题并返回空回答（无 choice → 确认被拒）。

        Asks the operator a question: when unattended, records the question and returns an
        empty answer (no choice → confirmation rejected).
        """
        self.rejected.append(question)
        return Answer()
```

`core/api/voice.py` —— `voice_answer` 中的校验段：

```python
    # choice 为结构化选择的取值（前端按钮回传）。此处只做「非空字符串」的形状校验，
    # 取值合法性由消费方（如权限策略层）自行判断 —— 这样新增选项集（允许一次 /
    # 永久允许 / 拒绝 …）无需改动本端点。
    #
    # choice carries the structured selection returned by the frontend's buttons. Only its
    # shape (a non-empty string) is validated here; whether a value is meaningful is up to
    # the consumer (e.g. the permission policy layer), so new option sets need no change here.
    raw_choice = params.get("choice")
    choice = raw_choice.strip() if isinstance(raw_choice, str) and raw_choice.strip() else None
    channel.answer(str(params.get("text") or ""), choice)
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_scheduler_runner.py tests/test_server.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add core/scheduler/runner.py core/api/voice.py tests/test_scheduler_runner.py tests/test_server.py
git commit -m "feat(API): /voice/answer 的 choice 放宽为任意非空字符串

取值合法性移交消费方（权限策略层需要 允许一次/永久允许/拒绝 等取值）。
_SilentChannel 补 kind/options 形参，无人值守仍返回空 Answer（fail closed）。"
```

---

## Task 6: 前端类型贯通

**Files:**
- Modify: `web/src/types.ts`（`QuestionEvent` 约 203-210 行）
- Modify: `web/src/api.ts`（`onQuestion` 约 212 行、`answer` 约 129 行）
- Modify: `web/src/composables/assistant/store.ts`（`PendingQuestion` 约 77-87 行）
- Modify: `web/src/composables/assistant/useChat.ts`（`onQuestion` 约 110 行、`sendAnswer` 约 152 行）
- Test: `web/src/api.spec.ts`、`web/src/composables/assistant/__tests__/useChat.spec.ts`

**Interfaces:**
- Consumes: 后端 Task 1 的事件形状
- Produces: `QuestionOption { value: string; label: string }`；`PendingQuestion { text, kind: 'choice'|'text'|'composite', options: QuestionOption[] }`；`answer(sessionId, text, choice?: string)`；`sendAnswer(text: string, choice?: string)`

- [ ] **Step 1: 写失败测试**

在 `web/src/api.spec.ts` 的 `streamUtter SSE` describe 中追加：

```ts
  // 选择类提问：kind 与 options 透传给 onQuestion
  // A choice question passes kind and options through to onQuestion
  it('question 事件的 kind 与 options 透传', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      body: sseStream([
        'data: {"type":"question","question":"确认执行吗？","session_id":"s1","kind":"choice","options":[{"value":"yes","label":"确认"},{"value":"no","label":"取消"}]}',
        'data: {"type":"done","session_id":"s1"}',
      ]),
    })
    vi.stubGlobal('fetch', mockFetch)
    const onQuestion = vi.fn()
    await streamUtter('hi', { onQuestion, onDone: vi.fn() })
    expect(onQuestion).toHaveBeenCalledWith({
      question: '确认执行吗？', session_id: 's1', kind: 'choice',
      options: [{ value: 'yes', label: '确认' }, { value: 'no', label: '取消' }],
    })
    vi.unstubAllGlobals()
  })
```

在 `web/src/composables/assistant/__tests__/useChat.spec.ts` 追加：

```ts
  /** 任意字符串 choice 都能透传（权限策略的 once / always 等）。 */
  it('任意字符串 choice 均可透传', async () => {
    currentSessionId.value = 's1'
    vi.mocked(api.answer).mockResolvedValue({ ok: true })
    await sendAnswer('', 'always')
    expect(api.answer).toHaveBeenCalledWith('s1', '', 'always')
  })
```

- [ ] **Step 2: 运行确认失败**

Run: `cd web && npx vitest run src/api.spec.ts src/composables/assistant/__tests__/useChat.spec.ts`
Expected: FAIL — `onQuestion` 收到的对象缺少 `kind`/`options`（断言不等）

- [ ] **Step 3: 实现**

`web/src/types.ts` —— 替换 `QuestionEvent`：

```ts
/**
 * 询问选项
 * Question option
 */
export interface QuestionOption {
  /** 机器可读取值。Machine-readable value. */
  value: string
  /** 展示文案。Display label. */
  label: string
}

export interface QuestionEvent {
  /** 事件类型。Event type. */
  type: 'question'
  /** 问题内容。Question content. */
  question: string
  /** 会话 ID。Session ID. */
  session_id: string
  /** 作答方式：text 自由文本 / choice 从选项选 / composite 选项加补充说明。
   *  How to answer: text (free input) / choice (pick an option) / composite (option plus a note). */
  kind: 'choice' | 'text' | 'composite'
  /** 选项列表（kind 为 choice / composite 时非空）。Options (non-empty for choice / composite). */
  options: QuestionOption[]
}
```

`web/src/api.ts` —— 两处：

```ts
  onQuestion?: (q: { question: string; session_id: string; kind: QuestionEvent['kind']; options: QuestionOption[] }) => void
```
（并在文件顶部类型 import 中加入 `QuestionOption`、`QuestionEvent`）

```ts
              h.onQuestion?.({ question: evt.question, session_id: evt.session_id, kind: evt.kind, options: evt.options })

  answer: (sessionId: string, text: string, choice?: string) =>
    post<ApiResponse>('/voice/answer', choice ? { session_id: sessionId, text, choice } : { session_id: sessionId, text }),
```

`web/src/composables/assistant/store.ts` —— 替换 `PendingQuestion`：

```ts
/** 待回答的提问（含作答方式与选项，决定前端渲染按钮还是输入框）。
 *  Pending question (with how to answer and its options, deciding whether the frontend
 *  renders buttons or an input). */
export interface PendingQuestion {
  /** 问题内容。Question content. */
  text: string
  /** 作答方式。How to answer. */
  kind: 'choice' | 'text' | 'composite'
  /** 选项列表（choice / composite 用）。Options (for choice / composite). */
  options: QuestionOption[]
}
```
（并在该文件顶部 `import type { ... } from '../../types'` 中加入 `QuestionOption`）

`web/src/composables/assistant/useChat.ts` —— 两处：

```ts
    onQuestion: ({ question, session_id, kind, options }) => {
      currentSessionId.value = session_id
      // kind 与 options 决定前端渲染按钮还是输入框；缺省按文本处理（向后兼容旧后端）。
      // kind and options decide buttons vs. an input; default to text for an older backend.
      pendingQuestion.value = {
        text: question,
        kind: kind === 'choice' || kind === 'composite' ? kind : 'text',
        options: options ?? [],
      }
      speakAuto(question)  // 澄清/确认问题也语音播报。Clarification/confirmation questions also voice broadcast.
      state.value = 'thinking'
    },
```

```ts
export async function sendAnswer(text: string, choice?: string) {
```

- [ ] **Step 4: 运行确认通过**

Run: `cd web && npx vitest run src/api.spec.ts src/composables/assistant/__tests__/useChat.spec.ts && npx vue-tsc --noEmit`
Expected: PASS，且类型检查无错（此时 `QuestionCard.vue` / `ConsoleTaskView.vue` 仍判 `kind === 'confirm'`，TypeScript 会报错 —— 属预期，由 Task 7/8 修复；若 vue-tsc 报错请直接继续 Task 8）

- [ ] **Step 5: 提交**

```bash
git add web/src/types.ts web/src/api.ts web/src/composables/assistant/store.ts web/src/composables/assistant/useChat.ts
git commit -m "feat(web): 询问类型贯通 — QuestionOption / 三值 kind / choice 放宽为 string"
```

---

## Task 7: `QuestionCard` 三态渲染

**Files:**
- Modify: `web/src/components/assistant/QuestionCard.vue`
- Test: `web/src/components/assistant/__tests__/QuestionCard.spec.ts`

**Interfaces:**
- Consumes: Task 7 的 `PendingQuestion { text, kind, options }`
- Produces: 组件按 `kind` 渲染三态；`composite` 下按钮与输入框任选其一均可提交

- [ ] **Step 1: 写失败测试**

在 `web/src/components/assistant/__tests__/QuestionCard.spec.ts` 中，把 `pendingQuestion.value = { text, kind: 'confirm' }` 全部改为 `kind: 'choice'` 并带上 `options`，然后追加：

```ts
/** 选项集的确认类（旧 confirm 已并入 choice）。 */
const CONFIRM_OPTIONS = [{ value: 'yes', label: '确认' }, { value: 'no', label: '取消' }]

  /** 综合类：按钮 + 输入框，只点按钮即可提交。 */
  it('composite 类只点按钮即可提交', async () => {
    currentSessionId.value = 's1'
    pendingQuestion.value = {
      text: '选一个并补充说明', kind: 'composite',
      options: [{ value: 'a', label: '甲' }, { value: 'b', label: '乙' }],
    }
    const w = mount(QuestionCard)
    expect(w.find('input').exists()).toBe(true)
    await w.findAll('button').find((b) => b.text() === '甲')!.trigger('click')
    await flushPromises()
    expect(api.answer).toHaveBeenCalledWith('s1', '', 'a')
  })

  /** 综合类：只输文本也可提交（不带 choice）。 */
  it('composite 类只输文本即可提交', async () => {
    currentSessionId.value = 's1'
    pendingQuestion.value = {
      text: '选一个并补充说明', kind: 'composite',
      options: [{ value: 'a', label: '甲' }],
    }
    const w = mount(QuestionCard)
    await w.find('input').setValue('我补充一下')
    await w.findAll('button').find((b) => b.text() === '回答')!.trigger('click')
    await flushPromises()
    expect(api.answer).toHaveBeenCalledWith('s1', '我补充一下', undefined)
  })
```

- [ ] **Step 2: 运行确认失败**

Run: `cd web && npx vitest run src/components/assistant/__tests__/QuestionCard.spec.ts`
Expected: FAIL — 三态未实现，`choice` 类不渲染按钮

- [ ] **Step 3: 实现**

`web/src/components/assistant/QuestionCard.vue` —— 模板与脚本：

```vue
<template>
  <!-- 提问卡片：按 kind 渲染成输入框 / 按钮 / 按钮加输入框（确认类即选项为确认与取消的 choice）。
       Question card: rendered per kind as an input, buttons, or buttons plus an input
       (a confirmation is just a choice whose options are confirm and cancel). -->
  <div v-if="q" class="confirm-card">
    <div class="confirm-title">❓ {{ title }}</div>
    <!-- 问题内容。Question content. -->
    <p class="confirm-q">{{ q.text }}</p>

    <!-- 选项按钮（choice / composite）。Option buttons (choice / composite). -->
    <div v-if="hasOptions" class="confirm-row">
      <button
        v-for="opt in q.options"
        :key="opt.value"
        class="confirm-btn"
        :class="{ primary: opt.value === 'yes' }"
        @click="choose(opt.value)"
      >{{ opt.label }}</button>
    </div>

    <!-- 文本输入（text / composite）。自由文本在 choice 下不会被接受，故不渲染。
         Text input (text / composite). Not rendered for choice, where free text is rejected. -->
    <div v-if="allowText" class="confirm-row">
      <input v-model="text" placeholder="输入回答后回车…" @keydown.enter="submit" />
      <button class="confirm-btn" @click="submit">回答</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useAssistant } from '../../composables/useAssistant'

/** 获取助手实例。Get assistant instance. */
const asst = useAssistant()

/** 待回答的提问（含作答方式与选项）。Pending question (with how to answer and its options). */
const q = asst.pendingQuestion

/** 卡片标题：按作答方式区分，让操作者一眼看出是确认还是追问。
 *  Card title: distinguished by how to answer, so the operator can tell a confirmation
 *  from a follow-up at a glance. */
const title = computed(() => (q.value?.kind === 'text' ? '需要你回答' : '需要你确认'))

/** 是否渲染选项按钮。Whether to render option buttons. */
const hasOptions = computed(() => !!q.value?.options.length)

/** 是否渲染文本输入（choice 下不渲染：自由文本会被后端判为未选择而拒绝）。
 *  Whether to render the text input (not for choice: free text is rejected by the backend
 *  as "no selection"). */
const allowText = computed(() => q.value?.kind !== 'choice')

/** 用户回答输入内容。User answer input content. */
const text = ref('')

/**
 * 提交自由文本回答：校验非空后发送并清空输入。
 * Submit a free-text answer: validate, send, then clear the input.
 */
function submit() {
  const v = text.value.trim()
  if (!v) return
  asst.sendAnswer(v)
  text.value = ''
}

/**
 * 提交选项回答：只回传选项的 value，不带文本。
 * Submit an option answer: returns only the option's value, with no text.
 *
 * @param value 选项的机器可读值。The option's machine-readable value.
 */
function choose(value: string) {
  asst.sendAnswer('', value)
}
</script>
```

样式块保持不变（`.confirm-card` / `.confirm-title` / `.confirm-q` / `.confirm-row` / `.confirm-btn` / `.confirm-btn.primary`）。

- [ ] **Step 4: 运行确认通过**

Run: `cd web && npx vitest run src/components/assistant/__tests__/QuestionCard.spec.ts`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add web/src/components/assistant/QuestionCard.vue web/src/components/assistant/__tests__/QuestionCard.spec.ts
git commit -m "feat(web): QuestionCard 三态渲染（按钮 / 输入框 / 按钮加输入框）

choice 下不渲染输入框：自由文本会被后端判为未选择而拒绝，给了只会让用户白输。
composite 下按钮与输入框并存，任选其一即可提交。"
```

---

## Task 8: `ConsoleTaskView` 三态

**Files:**
- Modify: `web/src/components/console/ConsoleTaskView.vue`
- Test: `web/src/components/console/__tests__/ConsoleTaskView.spec.ts`

**Interfaces:**
- Consumes: Task 6 的类型贯通
- Produces: 无新接口

- [ ] **Step 1: 写失败测试**

在 `web/src/components/console/__tests__/ConsoleTaskView.spec.ts` 中，把现有的 `kind: 'confirm'` 全部改为 `kind: 'choice'` 并补 `options`，再追加综合类用例：

```ts
  /** 综合类：按钮与输入框并存，只点按钮即可提交。 */
  it('composite 类只点按钮即可提交', async () => {
    vi.mocked(streamUtter).mockImplementation(async (_t: string, h: any) => {
      h.onQuestion?.({ question: '选一个并补充', session_id: 's1', kind: 'composite',
                       options: [{ value: 'a', label: '甲' }] })
      return 's1'
    })
    vi.mocked(api.answer).mockResolvedValue({ ok: true } as any)
    const w = mount(ConsoleTaskView)
    await w.find('textarea').setValue('做事')
    await w.findAll('button').find((b) => b.text() === '发送')!.trigger('click')
    await flushPromises()

    const card = w.find('.confirm-card')
    expect(card.find('input').exists()).toBe(true)
    await card.findAll('button').find((b) => b.text() === '甲')!.trigger('click')
    await flushPromises()
    expect(api.answer).toHaveBeenCalledWith('s1', '', 'a')
  })
```

- [ ] **Step 2: 运行确认失败**

Run: `cd web && npx vitest run src/components/console/__tests__/ConsoleTaskView.spec.ts`
Expected: FAIL — `isConfirm` 仍判 `'confirm'`，`choice` 类不渲染按钮

- [ ] **Step 3: 实现**

`web/src/components/console/ConsoleTaskView.vue`：

模板中 `confirm-card` 整段替换为：

```vue
    <!-- 澄清/确认问题卡片：按 kind 渲染成输入框 / 按钮 / 按钮加输入框。
         Clarification/confirmation card: rendered per kind as an input, buttons, or buttons plus an input. -->
    <div v-if="pendingQuestion" class="confirm-card">
      <div class="confirm-title">❓ {{ pendingQuestion.kind === 'text' ? '需要你回答' : '需要你确认' }}</div>
      <p class="confirm-q">{{ pendingQuestion.text }}</p>
      <!-- 选项按钮（choice / composite）。Option buttons (choice / composite). -->
      <div v-if="pendingQuestion.options.length" class="confirm-row">
        <UiButton
          v-for="opt in pendingQuestion.options"
          :key="opt.value"
          :variant="opt.value === 'yes' ? 'primary' : 'secondary'"
          size="sm"
          @click="choose(opt.value)"
        >{{ opt.label }}</UiButton>
      </div>
      <!-- 文本输入（text / composite）。choice 下不渲染：自由文本会被后端拒绝。 -->
      <div v-if="pendingQuestion.kind !== 'choice'" class="confirm-row">
        <UiInput v-model="answer" placeholder="输入回答后回车…" @keydown.enter="sendAnswer" />
        <UiButton variant="secondary" size="sm" @click="sendAnswer">回答</UiButton>
      </div>
    </div>
```

脚本中 `pendingQuestion` 的类型与 `isConfirm` 替换为：

```ts
/** 待回答的提问（含作答方式与选项，决定渲染按钮还是输入框）。
 *  Pending question (with how to answer and its options, deciding buttons vs. an input). */
const pendingQuestion = ref<{ text: string; kind: 'choice' | 'text' | 'composite'; options: { value: string; label: string }[] } | null>(null)
```

`onQuestion` 回调替换为：

```ts
    onQuestion: ({ question, kind, options, session_id }) => {
      if (session_id) sessionId.value = session_id
      // kind 与 options 决定渲染按钮还是输入框；缺省按文本处理（向后兼容旧后端）。
      // kind and options decide buttons vs. an input; default to text for an older backend.
      pendingQuestion.value = {
        text: question,
        kind: kind === 'choice' || kind === 'composite' ? kind : 'text',
        options: options ?? [],
      }
    },
```

`choose` 的签名放宽：

```ts
/**
 * 提交选项回答（choice / composite）：只回传选项值，不带文本。
 * Submit an option answer (choice / composite): returns only the option value, with no text.
 *
 * @param value 选项的机器可读值。The option's machine-readable value.
 */
async function choose(value: string) {
  if (!pendingQuestion.value) return
  const label = pendingQuestion.value.options.find((o) => o.value === value)?.label || value
  push('user', `（${label}）`)
  try {
    await api.answer(sessionId.value, '', value)
    pendingQuestion.value = null
  } catch (e) {
    push('error', '❌ 回答投递失败：' + formatError(e))
  }
}
```

同时删除不再使用的 `computed` import 中的 `isConfirm` 相关行（若 `computed` 不再被使用则一并从 `vue` 的 import 中移除）。

- [ ] **Step 4: 运行确认通过**

Run: `cd web && npx vitest run src/components/console/__tests__/ConsoleTaskView.spec.ts && npx vue-tsc --noEmit`
Expected: PASS，类型检查无错

- [ ] **Step 5: 提交**

```bash
git add web/src/components/console/ConsoleTaskView.vue web/src/components/console/__tests__/ConsoleTaskView.spec.ts
git commit -m "feat(任务tab): 询问三态渲染，与 QuestionCard 保持一致"
```

---

## Task 9: D —— 问答进聊天记录

**Files:**
- Modify: `web/src/composables/assistant/useChat.ts`（`onQuestion` 与 `sendAnswer`）
- Test: `web/src/composables/assistant/__tests__/useChat.spec.ts`

**Interfaces:**
- Consumes: Task 6 的 `sendAnswer(text, choice?)`、`addMessage(role, text)`
- Produces: 提问以 `assistant` 角色 + `❓ ` 前缀入 `messages`；回答以 `user` 角色入 `messages`，文本为被选 option 的 label（选择类）或输入文本（文本类）

- [ ] **Step 1: 写失败测试**

在 `web/src/composables/assistant/__tests__/useChat.spec.ts` 中：

**先在文件顶部补两个 mock**（`runTurn` 会调 `speakAuto`，且需要 `streamUtter` 可控）：

```ts
vi.mock('../useTts', () => ({ speakAuto: vi.fn() }))
```
并把已有的 api mock 补上 `streamUtter`：

```ts
vi.mock('../../../api', () => ({
  api: { answer: vi.fn(), callTool: vi.fn() },
  streamUtter: vi.fn(),
}))
```
并补 import：

```ts
import { messages, currentSessionId, pendingQuestion } from '../store'
import { runTurn, sendAnswer } from '../useChat'
import { streamUtter } from '../../../api'
```

**再追加该 describe**（提问入记录走 `runTurn` 的真实入口，避免只测一半）：

```ts
/** 问答进入聊天记录（需求 6）。Questions and answers enter the chat record. */
describe('useChat 问答入聊天记录', () => {
  beforeEach(() => {
    messages.value = []
    currentSessionId.value = ''
    pendingQuestion.value = null
    vi.mocked(api.answer).mockReset()
    vi.mocked(api.answer).mockResolvedValue({ ok: true })
    vi.mocked(streamUtter).mockReset()
  })

  /** 提问以 assistant 角色 + ❓ 前缀入记录（经 runTurn 真实入口）。 */
  it('提问以 assistant 角色入聊天记录', async () => {
    vi.mocked(streamUtter).mockImplementation(async (_t: string, h: any) => {
      h.onQuestion?.({ question: '确认执行吗？', session_id: 's1', kind: 'choice',
                       options: [{ value: 'yes', label: '确认' }] })
      return 's1'
    })
    messages.value = [{ id: 'm1', role: 'user', text: '做事', timestamp: Date.now() }]
    await runTurn()
    const q = messages.value.find((m) => m.role === 'assistant')
    expect(q?.text).toBe('❓ 确认执行吗？')
  })

  /** 选择类回答：以被选 option 的 label 入记录（不写机器值）。 */
  it('选择类回答以 label 入聊天记录', async () => {
    currentSessionId.value = 's1'
    pendingQuestion.value = {
      text: '确认执行吗？', kind: 'choice',
      options: [{ value: 'yes', label: '确认' }, { value: 'no', label: '取消' }],
    }
    await sendAnswer('', 'yes')
    const last = messages.value[messages.value.length - 1]
    expect(last?.role).toBe('user')
    expect(last?.text).toBe('确认')
  })

  /** 文本类回答：以输入文本入记录。 */
  it('文本类回答以输入文本入聊天记录', async () => {
    currentSessionId.value = 's1'
    pendingQuestion.value = { text: '目标位置？', kind: 'text', options: [] }
    await sendAnswer('桌面')
    const last = messages.value[messages.value.length - 1]
    expect(last?.role).toBe('user')
    expect(last?.text).toBe('桌面')
  })

  /** 投递失败时不写回答记录（避免记录与后端状态不一致）。 */
  it('投递失败时不写回答记录', async () => {
    currentSessionId.value = 's1'
    pendingQuestion.value = { text: '目标位置？', kind: 'text', options: [] }
    vi.mocked(api.answer).mockRejectedValue(new Error('会话已失效'))
    await sendAnswer('桌面')
    expect(messages.value.some((m) => m.text === '桌面')).toBe(false)
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd web && npx vitest run src/composables/assistant/__tests__/useChat.spec.ts`
Expected: FAIL — `messages` 为空（当前不会写入记录）

- [ ] **Step 3: 实现**

`web/src/composables/assistant/useChat.ts` —— `onQuestion` 增加提问入记录：

```ts
    onQuestion: ({ question, session_id, kind, options }) => {
      currentSessionId.value = session_id
      // kind 与 options 决定前端渲染按钮还是输入框；缺省按文本处理（向后兼容旧后端）。
      // kind and options decide buttons vs. an input; default to text for an older backend.
      pendingQuestion.value = {
        text: question,
        kind: kind === 'choice' || kind === 'composite' ? kind : 'text',
        options: options ?? [],
      }
      // 提问也进聊天记录（需求：回答和询问也在聊天记录里）。
      // Questions enter the chat record too (both questions and answers belong there).
      addMessage('assistant', '❓ ' + question)
      speakAuto(question)  // 澄清/确认问题也语音播报。Clarification/confirmation questions also voice broadcast.
      state.value = 'thinking'
    },
```

`sendAnswer` 增加回答入记录（**只在投递成功后写**）：

```ts
export async function sendAnswer(text: string, choice?: string) {
  const t = text.trim()
  // 结构化选择可以不带文本；两者皆空则不投递（避免空回答解除后端阻塞）。
  // A structured choice may carry no text; when both are empty, don't deliver
  // (avoiding an empty answer that would unblock the backend).
  if (!t && !choice) return
  if (!currentSessionId.value) return
  // 记录用文本：选择类取被选 option 的 label（人类可读），文本类取输入文本。
  // Record text: a choice takes the selected option's label (human-readable), a text answer its own text.
  const label = choice
    ? (pendingQuestion.value?.options.find((o) => o.value === choice)?.label || choice)
    : t
  try {
    await api.answer(currentSessionId.value, t, choice)
    addMessage('user', label)
    pendingQuestion.value = null
  } catch (e) {
    addMessage('system', '回答投递失败：' + formatError(e))
  }
}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd web && npx vitest run src/composables/assistant/__tests__/useChat.spec.ts`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add web/src/composables/assistant/useChat.ts web/src/composables/assistant/__tests__/useChat.spec.ts
git commit -m "feat(web): 提问与回答进入聊天记录

提问以 assistant 角色 + ❓ 前缀入 messages；回答以 user 角色入，
选择类记录 option 的 label 而非机器值。仅在投递成功后写记录，
避免记录与后端状态不一致。"
```

---

## Task 10: 全量验证与端到端

**Files:**
- Modify: `README.md`（询问类型说明）、`docs/architecture/roadmap.md`（P4 状态）

- [ ] **Step 1: 后端全量**

Run: `python -m pytest tests/ -q && python -m mypy core/ server.py`
Expected: 全部通过；mypy 无问题

- [ ] **Step 2: 前端全量**

Run: `cd web && npm test && npm run build`
Expected: 全部通过；vue-tsc 无错

- [ ] **Step 3: 确认无需重新生成 API 类型**

Run: `cd web && PYTHONIOENCODING=utf-8 python ../scripts/gen_openapi.py && npx --yes openapi-typescript@7.13.0 src/api/openapi.json -o /tmp/gen-check.ts && git diff --quiet src/api/generated.ts && echo "OK: 无 schema 变更"`
Expected: 输出 `OK: 无 schema 变更`

- [ ] **Step 4: 端到端人工验证（不可省 —— 本计划的过渡窗口只有到这里才关闭）**

先确认端口空闲再起服务（**Windows 上 `pkill` 不生效，务必用 `taskkill` 并检查 bind 成功**）：

```bash
taskkill //F //FI "IMAGENAME eq python.exe" ; sleep 2
netstat -ano | grep ":8520.*LISTENING" || echo "端口空闲"
python main.py serve > /tmp/server.log 2>&1 &
sleep 7 && grep -qa "10048" /tmp/server.log && echo "❌ bind 冲突，跑的是旧进程" || echo "✓ 绑定成功"
```

用 Playwright 或手工验证四条：
1. 控制台「对话」tab 发一条高风险任务 → 确认卡渲染 **选项按钮**（确认 / 取消），**无输入框**
2. 点「确认」→ 任务继续执行；点「取消」→ `cancelled`
3. 控制台「任务」tab 重复上述两条
4. 聊天记录里能看到 `❓ <问题>` 与回答文本

- [ ] **Step 5: 同步文档**

`README.md`：把 SSE 事件表中 `question` 的说明从「澄清/确认」更新为「`kind` 为 text / choice / composite，`options` 携带选项」。
`docs/architecture/roadmap.md`：P4 状态由 📋 待启动 改为 ✅ 已完成，并补计划链接。

- [ ] **Step 6: 提交并推送**

```bash
git add README.md docs/architecture/roadmap.md
git commit -m "docs: 同步询问类型说明与 P4 阶段状态"
git push origin main
```

---

## 完成标准

- [ ] `python -m pytest tests/ -q` 全绿（含新增的事件契约与容错用例）
- [ ] `python -m mypy core/ server.py` 无问题
- [ ] `cd web && npm test` 全绿
- [ ] `cd web && npm run build` 无类型错误
- [ ] `src/api/generated.ts` 无需变更（已核实 `missing` 未暴露到 API）
- [ ] 端到端四条人工验证通过（对话 tab / 任务 tab 各两条）
- [ ] 全仓无残留 `kind === 'confirm'`
