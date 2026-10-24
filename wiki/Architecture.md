# 架构总览

## 五层架构

```
┌──────────────────────────────────────────────────────────────┐
│  交互层  浏览器悬浮球(Vue3 + 本地 VAD) · 消息块渲染 · ASR/TTS   │
├──────────────────────────────────────────────────────────────┤
│  唤醒层  VAD 切段 → 本地 KWS 判定(sherpa-onnx) → ASR 抬指令     │
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

- `main.py` → `cli/` — 入口 CLI 分派（argparse 子命令 `serve` / `check`）
- `server.py` — FastAPI 装配（lifespan / 认证中间件 / CORS / 静态托管 / 挂载路由）
- `core/container.py` — 应用上下文容器（AppContext）：scheduler / MCP / LLM 连接池的生命周期统一启停
- `core/config/` — 配置包：schema（pydantic 模型）/ loader（YAML+密钥注入）/ runtime（单例+热重载+profile 解析）
- `core/prompts.py` — 系统提示词集中管理（编排各模块单一来源）；`core/model_compat.py` — 模型 profile 工具（协议分派/模型列表路径，2026-10-11 起无内置厂商目录）
- `core/api/` — **API 路由**：`voice`（子包：编排 SSE 入口 + 唤醒检测/快检/转写/TTS）/ `tools` / `memory` / `schedule` / `history`（会话历史）/ `library`（任务知识库）/ `sessions`（列表/改名/清空/分叉）/ `settings`（配置热重载）/ `providers`（拉取模型列表）/ `state`（会话注册表）；`schemas/` 分域 pydantic 响应模型（openapi 单一事实来源）
- `core/voice/` — 语音层：`streaming/`（WebSocket 会话：VAD→KWS→ASR→partial/final）/ `local/sherpa_onnx/`（四引擎 + registry）/ `wake.py`（拼音级唤醒判定）/ `call_funnel.py`（通话三级漏斗）/ `tts.py`
- `core/llm/` — 客户端（`client.py` 重试+熔断+连接池 / `stream.py` SSE 解析 / `protocols/`：openai · anthropic · gemini）
- `core/orchestrator/` — **编排层**：blocks（消息块协议）/ events（SSE 契约）/ session（状态机）/ intent / task / clarify / confirm / executor / condense（ReAct 历史滚动压缩）/ control / pipeline
- `core/session/` — 会话历史存储（SQLite `data/history.db`，对话线创建/改名/覆盖/删除）
- `core/tasks/` — 任务知识库（成功任务存档 + trigram 相似检索，减少重复询问）
- `core/agent/` — 多智能体：base 子代理基座 + coordinator 协调者
- `core/tools/` — @tool 注册中心 + 内置工具（29 个；`policy.py` 权限求值 / `describe.py` 元工具）
- `core/memory/` — 长期事实记忆（FTS5）+ 任务后提取 + 上下文注入
- `core/rag/` — 索引分块 + BM25 检索
- `core/detection/` — 检测域：environment（环境感知）/ validator（配置校验）/ connectivity（LLM/ASR/TTS 连通性）
- `core/mcp/`、`core/skills/`、`core/scheduler/` — 能力扩展
- `core/execution/` — shell / python / fs / gui 执行层

## 一次输入的处理链路

语音路径先过**唤醒层**：浏览器 AudioWorklet 采 20ms PCM → WebSocket
`/api/voice/asr/stream` → 本地 VAD 切段 → 本地 KWS 判定（未命中即丢弃）→ 本地增量 ASR
或云端整段转写 → `final` 文本带唤醒判定。随后进入 `core/orchestrator/pipeline.py`
的 `run_pipeline`：

1. **意图判断** `judge_intent`：规则（记忆类陈述）+ LLM 结构化输出 → 闲聊 或 任务
2. **任务形成** `form_task`：LLM 提取 `{goal, params, missing, risk}`
3. **澄清** `run_clarify`：把 `missing` 转问题问操作者，回答后回填，循环至信息足够（上限 3 轮）
4. **确认** `confirm_if_needed`：由 `permissions` 策略决定——**三档默认全放行**（2026-09-13 起，
   设置页「权限」或 `config.yaml` 可改回 `ask`/`deny`）；无人值守无确认通道时高风险一律拒绝
5. **执行** `execute_task`：复杂任务转多智能体协调者；简单任务走 ReAct 循环（read 工具并发）；
   历史超 `agent.condense_threshold_chars` 阈值时滚动压缩（`condense.py`，fail-open 不丢任务）
6. **汇报**：SSE `task_state(done)` 带 summary/steps；任务后异步提取事实写长期记忆；
   任务模式答「完成了」才存档任务知识库（`core/tasks/`）

> 所有层横切 **CancellationToken**（停止）与**审计日志**。

## 通话模式：三级判定漏斗

双击悬浮球进入通话模式后，段落**不走 KWS 唤醒链**：同一路 WebSocket 的 `final` 文本
交给服务端三级漏斗——每一级都「坏得静默、链路不断」。来源：
`docs/superpowers/specs/2026-10-05-call-mode-funnel-design.md`。

```
WS final 文本 → POST /api/voice/call/judge
  │
  ├─ L0 确定性粗筛（规则，零成本）
  │    · 通话会话未激活 → 丢
  │    · TTS 播报期 / 回声护栏窗口内 → 丢（ECHO_GUARD_MS=1200）
  │    · tab 无焦点（前端随段上报）且不在开放窗口期 → 丢
  │    · 段落 RMS 能量过低 / 时长 < 0.5s → 丢
  │
  ├─ L1 文本快筛（纯本地规则，零云端）
  │    · 空转写 / 标点 / 填充词 / 过短 → 丢（刻意保守）
  │
  └─ L2 云端精判（只为疑似命中的少数段付费）
       · LLM 意图闸门四分类：command / chitchat / bystander / unsure
         （开放窗口内连续 miss 达阈值后 relax：unsure 也算命中）
       · command/chitchat → 进 /api/voice/utter 编排 pipeline（零改动复用）
       · 其余 → 静默丢弃 + audit 记 call-funnel miss
```

- **降级**：L2 云端失败按未命中静默丢弃 + audit `call-funnel error`；本地 ASR 缺失只影响
  转写质量（`voice.asr.mode` 决定本地/云端/混合），不阻断漏斗。
- **开放窗口**：回答完成后 `voice.call.open_window_s`（默认 8s）内漏斗放宽（免 tab 焦点），
  鼓励连续追问；窗口过期回到严格粗筛。
- **互斥**：通话激活时 KWS 闸门暂停，`call/stop` 后恢复；唤醒入口保留在悬浮球 `.ball-mic` 徽章。
- 实施计划：`docs/superpowers/plans/2026-10-05-call-mode-funnel.md`。

## 数据流

- **下行**：交互层文本 → 编排层 → 智能体层 → 能力层 → 执行层
- **上行**：执行结果/工具输出 → 回喂智能体 → 编排层汇报 → 交互层（SSE / TTS）
- 会话完成后落盘 `data/tasks/<id>.json`（可审计、可回放）
