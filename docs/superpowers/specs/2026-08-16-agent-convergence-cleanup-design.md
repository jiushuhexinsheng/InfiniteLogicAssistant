# 语音智能体收敛与清理 — 设计文档

日期：2026-08-16
状态：待审批

## 背景

对项目做全景分析后，发现并确认要处理 4 项遗留问题：

| # | 问题 | 现状 |
|---|------|------|
| 3 | 双 agent 入口并存 | `/api/ai/chat`（旧 ReAct `run_agent`）与 `/api/voice/utter`（新编排 `run_pipeline`）是两条独立 SSE 管线；悬浮球/对话 Tab 仍用旧入口 |
| 4 | 前端旧文件残留 | `web/lib/wake-word.js`（旧关键词「小邮小邮」）与生效版 `web/public/lib/wake-word.js`（「小逻小逻」）并存，易误导 |
| 5 | RAG 索引非自动构建 | `core/rag/indexer.py` 已有 `index_sources()`，但 server 启动不调用，`rag/index.db` 是静态产物 |
| 6 | 桌面唤醒死代码 | `core/voice/wake.py`（桌面常驻监听）未接入 server 运行链路；桌面端已确定「不再回迁」（`desktop-ball` 分支） |

## 已确认需求（决策记录）

| 项 | 决定 |
|---|---|
| #3 收敛方式 | **前后端全面收敛**：前端对话也走编排管线；删除 `/api/ai/chat` 端点、`core/agent/legacy.py`、顶层 `core/agent.py` |
| #3 对话体验 | 保持现状水平：流式文本回复、工具时间轴、token 统计、澄清/确认内联问答；任务类答复也改为流式输出 |
| #5 建索引时机 | 启动时按需重建：`index.db` 缺失或源文件更新时重建；加 `rag.auto_index` 配置开关（默认开） |
| #6 桌面代码 | 全部删除 `wake.py` + `voice_smoke.py` + `test_voice_wake.py`，并清理仅它们使用的依赖（vosk/sounddevice）与配置字段 |

## 目标文件变更总览

```
后端（Python）
  server.py                      # /api/voice/utter 支持 messages 种子；删除 /api/ai/chat
  core/orchestrator/pipeline.py  # 接受 messages；chit_chat 带历史；把 events 传给 executor
  core/orchestrator/executor.py  # 流式发 tool_start/tool_end/usage/content_delta；ReAct 带会话上下文
  core/agent/__init__.py         # 去掉 legacy re-export
  core/agent/legacy.py           # 删除（run_agent）
  core/agent.py                  # 删除（顶层重复副本）
  core/voice/wake.py             # 删除
  core/config.py                 # 移除 wake_word.local_model；新增 rag.auto_index
  core/rag/__init__.py           # 新增 maybe_rebuild_index()
  requirements.txt               # 移除 vosk / sounddevice

前端（Vue3）
  web/src/api.ts                 # streamUtter 加 messages/signal + 补事件；删除 streamChat
  web/src/composables/assistant/store.ts   # buildHistory 去掉 system；新增 pendingQuestion/sessionId 状态
  web/src/composables/assistant/useChat.ts # 改用 streamUtter；sendAnswer()
  web/src/composables/useAssistant.ts      # 门面暴露 pendingQuestion / sendAnswer
  web/src/components/assistant/QuestionCard.vue  # 新增：问题回答卡片
  web/src/components/assistant/ChatInput.vue    # 内嵌 QuestionCard（悬浮球/控制台对话共用）
  web/src/styles/assistant.css         # 新增 .confirm-* 共享样式
  web/lib/wake-word.js           # 删除（残留副本）

测试
  tests/test_server.py           # 删 /api/ai/chat 用例；补 utter+messages 用例
  tests/test_agent.py            # 删除（测 legacy run_agent）
  tests/test_voice_wake.py       # 删除
  tests/test_orchestrator_pipeline.py  # 补 messages 种子 / 流式事件用例
  tests/test_orchestrator_executor.py  # 补 tool_start/tool_end/content_delta 用例
  tests/test_rag.py              # 补 maybe_rebuild_index 用例

文档
  README.md / roadmap.md / docs/architecture/01-voice-control-agent.md  # 同步引用
  config.yaml.example            # 补 rag 段
```

---

## 一、发现 4：删除前端残留（最简）

- 删除 `web/lib/wake-word.js` 与空目录 `web/lib/`。
- 该目录已在 `.gitignore`（`web/lib/`），纯磁盘清理，无 git 变更。
- 生效版本 `web/public/lib/wake-word.js` 不受影响。

## 二、发现 6：删除桌面唤醒死代码

删除文件：
- `core/voice/wake.py`（159 行，`WakeListener` / `is_stop_command`）
- `scripts/voice_smoke.py`（99 行，桌面监听冒烟）
- `tests/test_voice_wake.py`（22 行）

清理依赖与配置：
- `requirements.txt`：移除 `vosk==0.3.45`、`sounddevice==0.5.5`（grep 确认仅被上述 3 个文件引用）。
- `core/config.py`：移除 `voice.wake_word.local_model` 字段与相关注释；**保留** `model_path`（浏览器端 Vosk WASM 用）。
- 同步文档：README（§语音助手使用 桌面端说明、目录结构）、roadmap（桌面端章节）、架构文档（§3.1 语音、实现状态）中指向 `wake.py`/`voice_smoke.py`/`test_voice_wake.py` 的引用改写为「已移除」。

## 三、发现 5：RAG 启动按需建索引

新增 `core/rag/__init__.py::maybe_rebuild_index()`：

```python
async def maybe_rebuild_index(sources=DEFAULT_SOURCES) -> None:
    """index.db 缺失或任一源文件比索引新时重建；best-effort。"""
```

判定逻辑：
1. `INDEX_DB` 不存在 → 需要重建。
2. 存在 → 计算 `INDEX_DB.stat().st_mtime`；遍历 `sources`（文件取自身 mtime，目录取 `rglob` 内受支持后缀文件的最大 mtime）；任一源 `mtime > index_mtime` → 重建。
3. 重建调 `index_sources(sources)`，失败仅 `logger.warning` 不中断启动。

配置：
- `core/config.py` `DEFAULTS` 新增 `rag: {"auto_index": True}`。
- `config.yaml.example` 补充 `rag` 段及说明。
- `server.py` lifespan 在 MCP/调度器之后调用：`if cfg("rag.auto_index", True): await maybe_rebuild_index()`。
- 读取方 `core/rag/retriever.py` 不变（`rag_context()` 读 index.db，索引缺失时自然返回空）。

## 四、发现 3：双 agent 入口全面收敛（核心）

### 4.1 目标状态

- 唯一 agent 路径 = `run_pipeline`（`/api/voice/utter`）。
- 对话（悬浮球/控制台对话 Tab）与任务视图（控制台任务 Tab）共用同一编排管线，只是 UI 呈现不同。
- `run_agent`（legacy）及其端点、测试全部移除。

### 4.2 后端：接口与数据流

**`server.py` — `/api/voice/utter` 扩展**（删除 `/api/ai/chat`）：

```
请求体：{ text: str, messages?: [{role, content}] }
```
- `messages` 为前端最近 N 轮会话历史（**含**当前用户消息），作为多轮上下文种子。
- `run_pipeline(text, session, events, controller, messages=...)`。
- 会话注册、answer/stop、SSE 事件通道不变。

**`core/orchestrator/pipeline.py`**：

```
run_pipeline(text, session, events, controller, channel=None, messages=None)
```
- 种子：`if messages: session.messages = [m for m in messages if isinstance(m, dict)]`
  否则 `session.append("user", text)`（缺省行为，兼容 scheduler 无人值守等调用方）。
- `_chit_chat_reply(session, text, events)`：`messages = [system] + session.summary(8)`（含当前用户消息 → 多轮闲聊）。
- `execute_task(task, session, controller.token, events)`：把 `events` 队列传入执行器。

**`core/orchestrator/executor.py`**（新增流式事件，签名扩展）：

```
execute_task(task, session, cancel, events=None)
```
- ReAct 循环内：`events` 非空时，每次工具调用前后发射：
  - `tool_start` `{type, name, args}`
  - `tool_end`   `{type, name, status, output}`
  - `retry_stream_chat` 的 `usage` 事件透传 `{type:"usage", usage}`
- 最终答复：收敛后 `summary`（不再调工具时）以 `content_delta` 分块发射（≥512 字按 512 切块），再发 `task_state(done)`。
- 会话上下文：ReAct 初始 `history` 在 `[system, user(goal+params)]` 前，用 `session.summary()` 中**排除当前轮用户消息**后的历史行（`role:user/assistant`，不含 tool 行）前置为「对话历史」上下文（与 RAG/记忆注入并存，失败不影响执行）。
- 多智能体路径（`run_coordinator`）：保持现状，结束时给 `summary/steps`；事件通道仅在关键节点发 `task_state(notify)`（可选，V1 不细分）。

事件契约对齐后，`/api/voice/utter` 完整事件集：
`task_state / content_delta / reasoning_delta / tool_start / tool_end / usage / question / error / done`

**删除**：
- `core/agent/legacy.py`、`core/agent.py`（顶层重复副本）。
- `core/agent/__init__.py` 移除 `from core.agent.legacy import _trim_history, run_agent`；保留 base/coordinator re-export。
- 多智能体（`base.py` / `coordinator.py`）不受影响（不 import legacy）。

### 4.3 前端：对话切换到编排管线

**`web/src/api.ts`**：
- `streamUtter(text, h, opts?: {messages?, signal?})`：
  - body `{ text, messages }`；支持 `AbortSignal`（取消/停止）。
  - `UtterHandlers` 扩展：`onTaskState / onContent / onReasoning / onToolStart / onToolEnd / onUsage / onQuestion / onDone(sessionId) / onError / onAbort`。
  - 事件解析补 `reasoning_delta / tool_start / tool_end / usage`；`question` 只回调不终止流。
- 删除 `streamChat` 与 `ChatHandlers`。

**`web/src/composables/assistant/store.ts`**：
- `buildHistory()`：去掉 `SYSTEM_PROMPT` 注入，只返回最近 6 条 `{role, content}`（system 由后端各自注入）；`SYSTEM_PROMPT` 常量删除。
- 新增模块状态：`pendingQuestion = ref('')`、`currentSessionId = ref('')`。

**`web/src/composables/assistant/useChat.ts`**：
- `runTurn()`：改用 `streamUtter(text, handlers, {messages: buildHistory(), signal})`。
  - `onContent` → 流式文本（闲聊与任务答复统一）；
  - `onToolStart/onToolEnd` → 维护 `toolAcc` 时间轴（与现状一致）；
  - `onUsage` → 累计 token；
  - `onTaskState` → 映射状态机（understanding/executing → thinking/tool_calling）；
  - `onQuestion` → 设 `pendingQuestion` + `currentSessionId`；
  - `onDone` → flush、播报、state=done；
  - `onAbort`/`onError` → 与现状一致。
- 新增 `sendAnswer(text)`：`api.answer(currentSessionId, text)` 后清 `pendingQuestion`。
- `cancelTool`/`abortChat`：`abortController.abort()` 传给 `streamUtter`。
- `retryTool`：保持 `api.callTool` 重跑 + `runTurn()` 续轮。

**UI 问题回答卡片**（复用 ConsoleTaskView 交互模式）：
- 新增 `QuestionCard.vue`：读共享 `pendingQuestion`/`currentSessionId`，含问题文本 + 输入框 + 回答按钮 → `sendAnswer`。
- 内嵌进 `ChatInput.vue`（悬浮球面板与控制台对话共用组件）text 区上方：`pendingQuestion` 非空时渲染，一处实现两处生效。
- `useAssistant.ts` 门面暴露 `pendingQuestion` / `sendAnswer`。
- 样式：ConsoleTaskView 的 `.confirm-*` 是 scoped 样式，本次在 `assistant.css` 新增共享 `.confirm-*` 类（不改动 ConsoleTaskView）。

### 4.4 后端测试调整

- `tests/test_server.py`：删 `/api/ai/chat` 两个用例；补 `/api/voice/utter` 带 `messages` 种子用例（断言 session 收到历史）。
- `tests/test_agent.py`：删除（全测 legacy `run_agent`）。
- `tests/test_orchestrator_pipeline.py`：补「messages 种子 + 闲聊带历史」「任务执行流式事件」用例。
- `tests/test_orchestrator_executor.py`：补「tool_start/tool_end/content_delta/usage 发射」用例（monkeypatch TOOLS.acall）。
- 其余（multi-agent、RAG、memory 等）不受影响。

## 错误处理

- RAG 自动建索引失败 → `logger.warning`，不阻断启动（上下文注入本就「失败不影响执行」）。
- `messages` 种子非 dict / 结构异常 → 过滤丢弃，回退为空会话（不抛 500）。
- 对话中 question 未在客户端回答（如用户关闭页面）→ 客户端断开 → SSE 生成器 finally 取消 runner → `ask()` 抛 `CancelledError` 正常收敛，无悬挂会话。

## 非目标（本次不做）

- 桌面端 `desktop-ball` 分支内容不动。
- 多智能体（coordinator）细粒度实时事件流（V1 仅结束汇总）。
- RAG 向量化升级、索引增量更新、`/api/rag/reindex` 手动端点。
- 对话 Tab 与任务 Tab 的 UI 合并。
