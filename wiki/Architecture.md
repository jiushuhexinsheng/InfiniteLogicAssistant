# 架构总览

## 五层架构

```
┌──────────────────────────────────────────────────────────────┐
│  交互层  浏览器悬浮球(Vue3 + Vosk WASM 唤醒) · ASR/TTS 播报     │
├──────────────────────────────────────────────────────────────┤
│  编排层  Orchestrator:会话状态机 → 意图 → 任务 → 澄清 → 确认    │
│          → 执行 → 汇报（SSE 事件流 + 人类在环问答通道）         │
│          └── StopController / CancellationToken 贯穿所有层     │
├──────────────────────────────────────────────────────────────┤
│  智能体层 Agent:协调者 + 规划/执行/检索/批评 子代理(并发≤4)     │
├──────────────────────────────────────────────────────────────┤
│  能力层  Tools · MCP · Skills · RAG · Memory · Scheduler       │
├──────────────────────────────────────────────────────────────┤
│  执行层  Shell · Python · 文件系统 · 环境感知 · GUI 自动化      │
└──────────────────────────────────────────────────────────────┘
```

## 目录即架构

- `server.py` — FastAPI 装配（lifespan / 认证中间件 / CORS / 静态托管 / 挂载路由）
- `core/config/` — 配置包：schema（pydantic 模型）/ loader（YAML+密钥注入）/ runtime（单例+热重载+profile 解析）
- `core/api/` — **API 路由**：`voice`（编排 SSE 入口）/ `tools` / `memory` / `schedule` / `history` / `settings`（配置热重载）/ `providers`（厂商目录）/ `state`（会话注册表）
- `core/orchestrator/` — **编排层**：session / intent / task / clarify / confirm / executor / control / pipeline
- `core/agent/` — 多智能体：base 子代理基座 + coordinator 协调者
- `core/tools/` — @tool 注册中心 + 内置工具
- `core/memory/` — 长期事实记忆（FTS5）+ 任务后提取 + 上下文注入
- `core/rag/` — 索引分块 + BM25 检索
- `core/detection/` — 检测域：environment（环境感知）/ validator（配置校验）/ connectivity（LLM/ASR/TTS 连通性）
- `core/mcp/`、`core/skills/`、`core/scheduler/` — 能力扩展
- `core/execution/` — shell / python / fs / gui 执行层

## 一次输入的处理链路

`core/orchestrator/pipeline.py` 的 `run_pipeline`：

1. **意图判断** `judge_intent`：规则（记忆类陈述）+ LLM 结构化输出 → 闲聊 或 任务
2. **任务形成** `form_task`：LLM 提取 `{goal, params, missing, risk}`
3. **澄清** `run_clarify`：把 `missing` 转问题问操作者，回答后回填，循环至信息足够（上限 3 轮）
4. **确认** `confirm_if_needed`：`risk=read` 自动放行；`write/exec` 需明确确认（无人值守默认拒绝）
5. **执行** `execute_task`：复杂任务转多智能体协调者；简单任务走 ReAct 循环（read 工具并发）
6. **汇报**：SSE `task_state(done)` 带 summary/steps；任务后异步提取事实写长期记忆

> 所有层横切 **CancellationToken**（停止）与**审计日志**。

## 数据流

- **下行**：交互层文本 → 编排层 → 智能体层 → 能力层 → 执行层
- **上行**：执行结果/工具输出 → 回喂智能体 → 编排层汇报 → 交互层（SSE / TTS）
- 会话完成后落盘 `data/tasks/<id>.json`（可审计、可回放）
