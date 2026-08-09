# 后端异步化 + 原生工具调用 — 设计文档

日期：2026-08-09
状态：已确认（用户审批通过）

## 背景

本项目（无限逻辑·语音助手）后端为同步实现（requests + stdlib http.server），工具调用目前是**前端 JSON action 约定**（SYSTEM_PROMPT 让 LLM 返回 `{"action":...}`，前端 `handleAction` switch 分发）。参考成熟项目 InfiniteLogic 与 GitHub 轻量 agent 实现后，确认方向：

- 后端改造为**异步**（FastAPI + uvicorn + httpx），对齐 InfiniteLogic 架构
- 工具调用改为**后端原生 OpenAI function-calling**（`@tool` 注册中心 + ReAct 循环）
- LLM/ASR/TTS 全部转 async httpx
- 聊天端点改为 **SSE 流式**，前端逐段渲染

## 已确认需求（决策记录）

| 项 | 决定 |
|---|---|
| 技术底座 | 异步重构：FastAPI + uvicorn（ASGI 服务器）+ httpx（HTTP 客户端） |
| ASR/TTS | 一并转 async httpx（不再用 requests） |
| 工具范围 | 轻量工具（datetime / 安全计算器）+ 联网工具（duckduckgo 搜索 / wttr.in 天气免 key） |
| 工具调用 | 后端原生 OpenAI function-calling（`@tool` + TOOLS 注册中心 + ReAct 循环） |
| 流式 | 聊天端点 SSE 流式事件（content_delta / reasoning_delta / tool_start / tool_end / done / error） |
| 前端 | 消费 SSE 逐段渲染；删除前端 JSON action 解析；保留 ToolTimeline 展示 |
| 客户端加固 | 分级重试（429/5xx/timeout）+ 指数退避 + 熔断器 + httpx 连接池 |

## 新增依赖

```
httpx>=0.27.0            # LLM / ASR / TTS 异步 HTTP
fastapi>=0.110.0         # ASGI 应用（服务器 + SSE）
uvicorn[standard]>=0.27.0
duckduckgo-search>=6.0.0 # 联网搜索
# 可选（dev）：pytest / pytest-asyncio 用于工具注册中心与 agent 逻辑测试
```

> ⚠️ 部署影响：项目离线部署依赖 `scripts/libs/` 离线 wheel，新增依赖需 `pip download` 补齐。

## 目标文件结构

```
core/
├── llm/
│   ├── __init__.py        # 兼容旧接口（get_llm / get_asr / get_tts 改为 async 风格）
│   ├── stream.py          # stream_chat() — httpx 流式，解析 SSE → 事件（参照 InfiniteLogic src/llm.py）
│   └── client.py          # LlmClient — 重试 + 熔断 + 连接池（参照 src/llm_client.py）
├── voice/
│   └── __init__.py        # ASR / TTS 改 async httpx
├── tools/
│   ├── __init__.py        # 导入工具模块触发注册；导出 TOOLS
│   ├── base.py            # @tool 装饰器 + _ToolRegistry（参照 src/tools/base.py，零第三方依赖）
│   ├── datetime_tool.py   # 当前日期/时间
│   ├── calculator.py      # 安全算术（ast 白名单求值）
│   ├── search.py          # duckduckgo 搜索
│   └── weather.py         # wttr.in 天气（免 key）
├── agent.py               # ReAct 循环（参照 src/agent.py，适配聊天端点）
├── config.py              # 新增 agent / llm_client 配置段
└── server.py              # 重写为 FastAPI 应用（保留同名入口）
```

## 各模块设计

### 1. `core/llm/stream.py` — `stream_chat()`

异步生成器，httpx 流式解析 SSE，产出事件（对齐 InfiniteLogic）：

```
content_delta    {"type":"content_delta","text":str}
reasoning_delta  {"type":"reasoning_delta","text":str}
tool_call_delta  {"type":"tool_call_delta","index":int,"id":str,"name":str,"arguments":str}
done             {"type":"done","message":{role,content,tool_calls?}}
```

- 从当前 LLM profile 读取 endpoint / model / api_key / chat_path（`resolve_llm_profile`）
- 请求体：`{model, messages, tools?, tool_choice:"auto", stream:true, stream_options:{include_usage:true}}`
- 按 index 累积 `tool_call` 片段（参照 `_accumulate_tool_calls`）

### 2. `core/llm/client.py` — `LlmClient`

异步封装 `stream_chat`，提供：

- **连接池**：共享 `httpx.AsyncClient`（Keep-Alive，max_connections=20）
- **分级重试**：可重试状态码 `{429,502,503,504}`；不可重试 `{400,401,403,404,422}`；网络错误（timeout/connect）可重试
- **指数退避 + jitter**：`base * 2^(attempt-1)`，封顶，±25% 抖动；429 尊重 `Retry-After`
- **熔断器**：CLOSED(连续N失败)→OPEN(冷却T)→HALF_OPEN(单探针)；成功复位
- 方法：`async retry_stream_chat(messages, tools)`；`get_llm_client()` 单例

配置（新增 `core/config.py` 段，带默认值）：
`agent_recursion_limit=6`、`agent_max_history_messages=40`、`llm_retry_max=3`、`llm_retry_backoff_base=0.5`、`llm_retry_backoff_max=10`、`llm_circuit_breaker_threshold=5`、`llm_circuit_breaker_cooldown=30`、`llm_request_timeout=60`

### 3. `core/tools/base.py` — `@tool` 注册中心

参照 InfiniteLogic `src/tools/base.py`（**不引入 pydantic**，纯 stdlib：`inspect` + `typing`）：

```python
@tool("获取当前日期与时间")
def get_datetime() -> str: ...

TOOLS.schemas()          # → OpenAI tools 数组
TOOLS.acall(name, args)  # async 执行；异常转 "Error: ..." 字符串
```

- `_build_schema(func, description)`：从 `inspect.signature` + `get_type_hints` 推导 `{type:"function",function:{name,description,parameters}}`
- 类型映射：str/int/float/bool/list/dict → JSON Schema；缺省 fallback string
- `TOOLS` 模块级单例；`core/tools/__init__.py` 导入各工具模块触发注册

### 4. 内置工具

| 工具 | 签名 | 说明 |
|---|---|---|
| get_datetime | `() -> str` | 当前日期时间 |
| calculate | `(expression: str) -> str` | **安全**算术：ast 解析白名单（num/binop/name 常量），禁 exec/eval 危险节点 |
| web_search | `(query: str) -> str` | duckduckgo 搜索，返回前 N 条标题+链接+摘要 |
| get_weather | `(city: str) -> str` | wttr.in（免 key）`curl wttr.in/{city}?format=...`，httpx 请求 |

### 5. `core/agent.py` — ReAct 循环

参照 InfiniteLogic `src/agent.py`（聊天端点用简化版）：

```
run_agent(messages, tools) -> async events:
  1. 从请求 messages 起步（前端已带历史）
  2. 调 retry_stream_chat(trimmed, tools=TOOLS.schemas())
  3. assistant message 无 tool_calls → yield done，结束
  4. 有 tool_calls → 解析 args → TOOLS.acall → 追加 tool message → 回第 2 步
  5. step 超 agent_recursion_limit → error
```

- 历史裁剪：保留前导 system + 最近 N 条，不切断 tool_call↔tool 配对（参照 `_trim_history`）
- 事件流：`content_delta` / `reasoning_delta` / `tool_start` / `tool_end` / `done` / `error`
- 工具执行串行（本项目工具轻量，无需并行分组）

### 6. `core/server.py` — FastAPI 应用

- 保持入口 `python main.py serve` 与默认端口 8520
- 端点：
  - `GET /api/ping`
  - `GET /api/config`
  - `POST /api/voice/transcribe`（async httpx ASR）
  - `POST /api/ai/chat` → **SSE**（`StreamingResponse`, `text/event-stream`）：请求 `{messages}`，流式产出上述事件
- 静态托管 `web/dist`（FastAPI `StaticFiles` + SPA 兜底）
- `main.py test` 适配 async（asyncio.run）
- TTS 后端 `_play_audio` 逻辑保留（浏览器默认 SpeechSynthesis 为主）

### 7. 前端变更

- `api.ts` 新增 `streamChat(messages, handlers)`：`fetch` + `ReadableStream` 解析 SSE `data:` 行
- `useAssistant.handleLLM` 改为消费 SSE：
  - `content_delta` → 累积成 assistant 消息（支持流式打字机）
  - `tool_start` / `tool_end` → 在消息上建/更新 ToolCall，驱动 ToolTimeline
  - `done` → 完成；`error` → 出错态
- **删除** `SYSTEM_PROMPT` 中的 `{"action":...}` JSON 约定与 `handleAction` 前端分发（工具由后端原生调用）
- 保留 ToolTimeline / 状态机 / 语音链路

## 分阶段实施

- **阶段 A（异步地基）**：依赖、FastAPI 服务器、`stream_chat`、LLM/ASR/TTS 转 httpx；旧 4 端点可用
- **阶段 B（工具层）**：`@tool` 注册中心 + datetime/calculator/search/weather；pytest 测试工具
- **阶段 C（ReAct + 加固）**：`agent.py` 循环 + 重试/熔断；`/api/ai/chat` 出 SSE
- **阶段 D（前端 SSE）**：流式聊天 + 工具时间轴 + 移除前端 JSON action

## 保持不变（迁移安全）

- 对外 HTTP 端点路径不变（`/api/ping` `/api/config` `/api/ai/chat` `/api/voice/transcribe`）
- 语音链路（唤醒→ASR→发消息→LLM→播报）语义不变
- 配置 profile 机制保留（多服务商切换）
- `main.py serve` / `main.py test` 命令保留

## 验收标准

1. `python main.py serve` 启动，4 端点可用；`/api/ai/chat` 返回 SSE 流
2. `npm run build` 通过；前端语音 + 流式聊天 + 工具时间轴正常
3. `@tool` 注册中心：`TOOLS.schemas()` 生成正确 OpenAI schema；`TOOLS.acall` 执行正确
4. ReAct 循环：LLM 请求工具时正确执行并回喂，最终回答含工具结果
5. 熔断/重试：模拟 429/5xx 时按策略退避重试；连续失败触发熔断
6. ASR/TTS 异步可用；`main.py test` 连通性测试通过
7. 新增依赖已补入 `scripts/libs/` 离线 wheel（离线安装可跑）
