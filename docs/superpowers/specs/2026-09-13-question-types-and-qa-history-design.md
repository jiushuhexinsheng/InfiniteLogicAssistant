# 询问类型扩展 + 问答进聊天记录 设计文档（P4 / 子系统 B+D）

日期：2026-09-13
状态：待实施
上游：[Agent 能力扩展路线图（P4–P8）](2026-09-13-agent-capabilities-roadmap-design.md) 的子系统 B + D

## 背景

当前询问只有两种类型：`clarify`（自由文本）与 `confirm`（固定「确认 / 取消」两选项）。路线图要求扩展为**选择 / 文本 / 综合**三类，并把提问与回答落进聊天记录。

勘察发现的关键约束：**子系统 A（权限策略层）需要「允许一次 / 永久允许 / 拒绝」三选项**。若把 `confirm` 保留为独立类型、再新增 `choice`，A 就需要第四个类型或另起一套机制。因此本轮把 `confirm` **泛化**为「`choice` + 两个固定选项」，使任意选项集（含 A 的三选项）复用同一套机制。

## 已确认决策

| # | 决策 | 理由 |
|---|---|---|
| 1 | `kind` 泛化为 `choice \| text \| composite`，**`confirm` 并入 `choice`** | confirm 只是 choice 的特例；保留两套语义会分叉，且 A 的三选项无法复用 |
| 2 | 综合类**任选其一**（按钮或文本，也可两者都给） | `Answer(text, choice)` 已是两个独立字段，天然支持；强制两者都填与「减少询问」相左 |
| 3 | 询问类型由 **LLM 判定 + 编排层兜底** | 与现有 `judge_intent` / `form_task` 风格一致；编排层对固定场景硬编码，不依赖模型 |
| 4 | **不新增 `ChatMessage.kind`** | 需求原文只说「在聊天记录里」；加字段会波及 `buildHistory` / `ConsoleMessageList` / `persist`，属 YAGNI |
| 5 | 问答**自动进 `buildHistory()`** | 模型能看到自己问过什么，对多轮有益；已有 6 条上限约束，不会膨胀 |

## 数据模型

```python
# core/orchestrator/events.py
class QuestionOption(BaseModel):
    """选择项：value 为机器可读取值，label 为展示文案。"""
    value: str
    label: str

class QuestionEvent(_BaseEvent):
    type: Literal["question"] = "question"
    question: str
    session_id: str = ""
    kind: Literal["choice", "text", "composite"] = "text"
    options: list[QuestionOption] = []   # choice / composite 使用；text 时为空
```

`Answer`（`core/orchestrator/session.py`）**结构不变** —— 已有 `text: str` 与 `choice: str | None` 两独立字段，直接满足「综合类任选其一」。

通道契约：`OperatorChannel.ask(question, *, kind="text", options=None) -> Answer`。

## 后端变更

| 文件 | 变更 |
|---|---|
| `orchestrator/events.py` | 新增 `QuestionOption`；`QuestionEvent` 加 `kind`（三值）/ `options`，移除 `clarify`/`confirm` 二值 |
| `orchestrator/session.py` | `OperatorChannel.ask` / `Session.ask` 增 `kind` + `options` 参数；`Answer` 不变 |
| `orchestrator/pipeline.py` | `EventQueueChannel.ask` 透传 `kind`/`options`；`answer(text, choice)` 不变 |
| `orchestrator/confirm.py` | `_ask_operator` 发 `kind="choice"` + `options=[{yes,确认},{no,取消}]`；`_resolve_confirm` 语义不变（仍读 `choice == "yes"`） |
| `orchestrator/clarify.py` | 按 `MissingItem.type/options` 提问；`choice` 回答解析为对应 option 的 `label` 用于回填 |
| `orchestrator/task.py` | 新增 `MissingItem`；`Task.missing` 由 `list[str]` 改为 `list[MissingItem]`；`form_task` 的 tool schema 与解析同步 |
| `scheduler/runner.py` | `_SilentChannel.ask` 补 `kind`/`options` 形参（无人值守仍返回空 `Answer`） |
| `api/voice.py` | `/voice/answer` 的 `choice` 校验从 `("yes","no")` 放宽为「非空字符串」 |

### `MissingItem` 与解析兜底

```python
@dataclass
class MissingItem:
    question: str
    type: str = "text"                       # text | choice | composite
    options: list[dict] = field(default_factory=list)   # [{value,label}]
```

`form_task` 的 `missing` 从 `list[str]` 变为对象数组，解析时**必须容错**：

- 元素是字符串 → `MissingItem(question=str)`（模型不遵守 schema 时的兜底）
- `type` 缺失或非法 → `"text"`
- `type` 为 `choice`/`composite` 但 `options` 为空 → **降级为 `text`**（没有选项的选择题无法作答）

这三条容错是必须的：`form_task` 依赖 LLM 输出，schema 不保证被遵守。

### `clarify` 的 `choice` 回填

`run_clarify` 把回答累积进 `answered` 再重 `form_task`。对 `choice` 类回答，回填**option 的 `label`**（人类可读，便于模型理解）而非 `value`；`value` 在 options 中找不到时回退为原始 `value`。

`asked` 去重由 `str` 改为按 `item.question` 比较。

## 前端变更

| 文件 | 变更 |
|---|---|
| `types.ts` | `QuestionEvent` 增 `kind`（三值）/ `options`；`answer` 的 `choice` 由 `'yes'\|'no'` 放宽为 `string` |
| `api.ts` | `UtterHandlers.onQuestion` 签名同步；`answer(sessionId, text, choice?: string)` |
| `composables/assistant/store.ts` | `PendingQuestion` 增 `options: {value,label}[]`、`kind` 三值 |
| `composables/assistant/useChat.ts` | `onQuestion` 透传 `options`；`sendAnswer(text, choice?)` 类型放宽；**D**：提问时 `addMessage('assistant', '❓ ' + question)`，回答成功后 `addMessage('user', 回答文本)` |
| `components/assistant/QuestionCard.vue` | **三态渲染**：`text` → 输入框；`choice` → 按 `options` 渲染按钮；`composite` → 按钮 **+** 输入框，任选其一即可提交 |
| `components/console/ConsoleTaskView.vue` | `isConfirm` 改为按 `kind === 'choice'` 渲染选项按钮；`composite` 同步（按钮 + 输入框）。**D 不改本组件**：它不用助手 store，而用自有的任务执行日志，问答本已以「（回答）」形式记在日志里 |

### 选择类回答的文本形式（D 用）

按钮回答也要在聊天记录里留下可读文本。取被选 option 的 `label`（如「确认」「取消」），不写机器值。

## 测试策略

**后端（TDD）**
- `QuestionEvent` 的 `kind`/`options` 序列化；`text` 类不含 options
- `confirm_if_needed` / `confirm_tool` 发出 `kind="choice"` 且 options 恰为 确认/取消
- `_resolve_confirm` 行为不变（回归：原有结构化确认用例全部保留）
- `MissingItem` 解析的三条容错路径（字符串元素 / type 缺失 / options 为空降级）
- `run_clarify` 对 `choice` 类回答按 label 回填、按 question 去重
- `/api/voice/answer` 接受任意非空 choice（`once` / `always` 不再被拒）

**前端（Vitest）**
- `QuestionCard` 三态渲染；`composite` 下「只点按钮」「只输文本」「两者都给」三种提交均有效
- 按钮回答带 `choice`、文本回答不带
- **D**：提问进 messages（assistant 角色 + `❓` 前缀）、回答进 messages（user 角色，文本为 label）

**全量**：`pytest` + `mypy` + `npm test` + `npm run build`

## 风险

| 风险 | 处置 |
|---|---|
| **`Task.missing` 结构变更是本轮最重的一处** | `task.py` / `clarify.py` / `Task` 序列化（`state.py` 的 `asdict`）及其测试都要动；`asdict` 对嵌套 dataclass 原生支持，无需额外处理 |
| **`confirm` → `choice` 会改动上一轮刚建的确认链路及其测试** | 行为不变（仍 `choice == "yes"` 判定）；改动集中在 `kind` 取值与前端 `isConfirm` 分支 |
| **`choice` 校验放宽后校验责任转移到消费方** | 有意解耦：A 的权限策略层必须自行校验 `once`/`always` 合法性。本轮在 `api/voice.py` 注释中写明该契约 |
| LLM 不遵守 `missing` 新 schema | 三条容错兜底；`form_task` 已有的 try/except 兜底保持不变 |

## 不做（明确排除）

- 不新增 `ChatMessage.kind`（决策 4）
- 不为 `composite` 强制要求两者都填（决策 2）
- 不改 `Answer` 结构
- 不实现 A 的权限策略本身（本轮只提供其所需的选项集能力）
- 不做问答消息的视觉区分（emoji 前缀足够）
- **D 不改 `ConsoleTaskView`**：它不使用助手 store，而维护自有的任务执行日志，问答已以「（回答）」形式记录在其中。D 的范围限定为 `useChat` 通路（悬浮助手 + 控制台「对话」tab），即 `messages` 这一份聊天记录
