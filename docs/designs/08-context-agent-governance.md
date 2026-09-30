# 08 · 上下文与多智能体治理：滚动压缩 + 工具输出截断/渐进加载 + 委派规范

> 借鉴：OpenHands Condenser（滚动窗口压缩）、Leon 2.0（渐进式工具 schema + 有界预览）、
> Anthropic 多智能体实践（委派四要素、产物落文件只回传引用）、Claude Code（ACI 防呆）。
> 优先级 P4。纯 `executor` / `agent/` / `prompts.py` 内部改动，不碰事件契约（通知走既有 task_state notify）。

## 实施状态

- **批1 LLM 口径截断**：第四口径 `blocks.llm_tool_feed`（读 `tools.llm_max_output_chars`，
  默认 8000、0=不限，截断附「grep_file/read_file 分段取」指引）；executor 的 tool 历史消息
  用截断正文、steps/块仍用原文（`full_len` 保持原始长度）；agent/base 同口径；四口径在
  `blocks.py` 常量区并立声明。
- **批2 滚动压缩**：新模块 `orchestrator/condense.py`（头 2 尾 6、超 `agent.condense_threshold_chars`
  折叠中间段为 `[上下文压缩]` 摘要；**孤儿 tool 处理方向 = cut 后移把尾段开头连续孤儿划给
  被压段**——首版方向写反已被测试抓出；fail-open：摘要失败原样返回；入参不原地改）；
  executor 每步前调用并 `session.notify` 可见；子代理循环同点（log 级）。
- **批3 委派规范**：`_DECOMPOSE_SYSTEM` 扩写四要素 + 努力度预算；schema `maxItems: 6` +
  `output_format`/`boundary` 字段（run_one 拼进 goal 下达）；子代理完整产物落
  `data/agent_outputs/<session>/`，executed 留 300 预览 + artifact 路径，critic 提示携带
  「完整产物」路径并提示可 read_file 读全文；executor 汇总 steps 附 `[产物] 路径`。
- **批4 渐进式 schema**：`@tool(group=...)` + `TOOLS.schemas(stub_groups=...)`（降级组
  parameters 置空 + 描述标注先调 describe）；MCP 工具注册归 `mcp` 组；新元工具
  `tools_describe`（core 组、永远完整下发）；executor/base 按 `tools.lazy_groups` 传参
  （默认 `[]` = 全量下发零变化）；`DESCRIBE_NOTE` 仅 lazy 开启时附进 system。
- **配置三处同步**：`agent.condense_threshold_chars` / `tools.llm_max_output_chars` /
  `tools.lazy_groups`（schema + AgentConfigOut/ToolsConfigOut + configDefs + example）。
  `lazy_groups` 是 list 类型，设置页控件不支持 → **config-file only**（与 kws 同）。
- 测试：pytest 524 绿（新增 condense 4、decompose schema、artifact+critic 路径、
  截断集成、lazy schema 3）、vitest 259 绿、mypy 干净、gen:api/build 通过。

## 1. 现状（问题定位）

| # | 现状 | 位置 | 问题 |
|---|---|---|---|
| 1 | **工具 schema 每轮全量下发**（含 MCP 全部工具） | `executor.py:102`、`agent/base.py:93` | 工具越多 prompt 越肥，MCP 挂 10 个 server 即爆炸 |
| 2 | **工具结果对 LLM 全文回喂**，无截断（截断只在展示/落库层：PREVIEW 500 / HISTORY 4000） | `core/tools/base.py:193-204`、`executor.py:153` | 一次 `read_file` 整本大文件可打爆上下文 |
| 3 | ReAct 循环**无压缩机制**，只靠 `recursion_limit=12` 硬停 | `executor.py` 循环、`schema.py:272-286` | 长任务历史线性膨胀 |
| 4 | 子代理回传：executed 存 `output[:300]`、critic 吃这 300 字、critic 输出 `[:500]` | `coordinator.py:134-137,163-173` | critic 基于二手残缺信息审查；最终 summary 也窄 |
| 5 | 拆解 prompt 无数量上限、无边界/输出格式约束（schema 只有 goal/agent_type/independent） | `prompts.py:68-69`、`coordinator.py:26-50` | 子任务可无限膨胀；委派质量靠模型自觉 |
| 6 | 历史种子仅前端 `buildHistory` 最近 6 条 | `store.ts:325-345` | ✅ 已有节流，保持 |

## 2. 目标行为

1. **有界上下文**：长任务自动压缩中间历史（保留头尾 + 摘要），不丢任务连续性、不破 tool 语义。
2. **输出有界**：LLM 视角的工具结果有统一上限与「如何取更多」指引。
3. **schema 可选渐进加载**：核心工具全 schema，扩展工具一行简介 + `tools_describe` 按需取（opt-in）。
4. **委派结构化**：子任务带输出格式/边界/数量上限；子代理完整产物落文件，critic 读文件而非 300 字残片。

## 3. 设计

### 3.1 滚动压缩（Condenser）

新模块 `core/orchestrator/condense.py`：

```python
async def maybe_condense(history: list[dict], client, *, threshold_chars: int) -> tuple[list[dict], int]:
    """超阈值时压缩中间段，返回 (新历史, 省略条数)。未超阈原样返回。"""
```

- **触发**：估算字符数 `sum(len(str(m.get("content",""))) for m in history) > agent.condense_threshold_chars`（默认 **12000** ≈ 3k tokens，字符估算免分词器依赖）。
- **切法**（OpenHands head+tail 的同构）：
  - 保留：system 邻接的前 2 条（首轮任务描述）+ 最近 **6** 条；
  - 中间段 → 一次 LLM 调用生成摘要（复用 `agent.structured_temperature`），产出一条 `{"role":"assistant","content":"[上下文压缩] …摘要…"}`；
  - **关键清洗**：中间段若含未闭合的 `tool_calls` / 孤儿 `role:"tool"` 消息，压缩时**整段折叠**——把工具调用结果的关键结论并入摘要文本、删除 `tool_calls` 字段（否则 OpenAI 兼容端点会因 tool 消息无前置 call 报 400）。这是本设计最容易踩的坑，单独立测试。
- **可见性**：压缩后 `session.notify("上下文已压缩（省略 N 条中间消息）")` → 走既有 `task_state notify` → notice 块，用户可见可审计。
- **调用点**：`executor.py` 每次 `retry_stream_chat` 前；`agent/base.py` subagent 循环同点（子代理步数更长，收益更大）。**只在任务执行内生效**，不动种子历史（`messages` 入参保持原样，避免污染会话持久化——压缩仅是本轮 LLM 视角）。
- 配置：`agent.condense_threshold_chars: int = 12000`（0=禁用；三处同步）。

### 3.2 LLM 视角工具输出截断（先做，收益最大）

- `executor.py:153` 与 `agent/base.py` 组装 tool 消息处，`content` 统一：

```python
TOOL_LLM_MAX_CHARS = config.settings.tools.llm_max_output_chars   # 默认 8000
if len(result) > TOOL_LLM_MAX_CHARS:
    result = result[:TOOL_LLM_MAX_CHARS] + f"\n…(输出已截断，共 {len} 字；可用 grep_file/read_file 分段获取)"
```

- **边界澄清**：截断只影响喂 LLM 的字符串；`ToolEndEvent.output`（PREVIEW_LEN=500）、落库（HISTORY_LEN=4000）、audit 全部不变——三口径并存是现状设计（`blocks.py:26-33`），本设计新增第四口径「LLM 口径」并在 `blocks.py` 常量区并排声明，避免口径散落。
- 配置：`tools.llm_max_output_chars: int = 8000`（`ToolsSection` 已有字段先例，`schema.py:305-314`）。

### 3.3 渐进式工具 schema（opt-in）

- `@tool(...)` 增加 `group: str = "core"` 参数（`base.py:263-285`）；MCP 工具默认归 `"mcp"` 组（`mcp_bridge.py:60-61` 注册处）。
- `TOOLS.schemas()` 改为 `schemas(groups: set[str] | None)`：
  - `core` 组 → 完整 schema（现状）；
  - 未在激活组的工具 → 一行 stub：`{"name", "description", "x-need-describe": true}`（无 `parameters`）。
- 新增只读工具：

```python
@tool("查询指定工具的完整参数 schema（名字列表）", risk="read")
async def tools_describe(names: list[str]) -> str: ...   # 返回 JSON {name: schema}
```

- 配置：`tools.lazy_groups: list[str] = []`（默认空 = 全量下发，**现状零变化**；填 `["mcp"]` 即 MCP 工具走渐进）。
- `EXECUTOR_SYSTEM` 补一句（`prompts.py`）：「工具列表若标注需要 describe，先调用 tools_describe 获取参数再调用」。
- **验收口径**：lazy 开启时首轮 prompt 工具 token 数可测下降（测试断言 stub 形状）。

### 3.4 多智能体委派规范

**（a）拆解 schema 与 prompt（`coordinator.py:26-50` + `prompts.py:68-69`）**：

- `_DECOMPOSE_TOOL` 增加：`"maxItems": 6`（子任务上限）+ 每项可选 `output_format`（string，期望输出形态）、`boundary`（string，「只做什么、不做什么」）。
- `DECOMPOSE_SYSTEM` 扩写为四要素措辞：每个子任务必须想清楚 **目标 / 输出格式 / 建议工具与来源 / 边界**；并注入 Anthropic 的努力度预算语句（「简单任务 1-3 个子任务、每个 3-10 次工具调用；仅确需并行才拆 ≥4 个」）。

**（b）产物落文件 + critic 读全文（`coordinator.py` + `agent/base.py`）**：

```
子代理完成 → run_subagent 把完整 output 写 data/agent_outputs/{turn_id}/{idx}.md
           → SubAgentResult 增字段 artifact: str | None（文件路径）
executed 记录保持 output[:300] 预览 + artifact 路径
critic 输入 = 各 {goal, preview[:600], artifact_path} 列表
           + 指令「可先用 read_file 查看 artifact 全文再审查」
critic 是子代理 → 天然带工具（agent/base 循环现成）→ 它真的会去读
最终 summary 聚合逻辑不变（merged + [审查]）
```

- 解决 300 字二手审查问题，且不增加 coordinator 上下文负担（路径 + 预览）。
- `data/agent_outputs/` 进 gitignore（`data/` 已整体忽略）；随会话清理策略暂不接（文件小，阶段二随 07 的会话删除联动）。
- 前端：executed 里 `artifact` 路径渲染为 tool 块 meta 附加行「完整产物: …」（`normalize.ts` tool_end 已收 meta 字段，additive）。

**（c）保持不变**：`Semaphore(4)` 并发、`agent:` 归属徽章事件、confirm 回调链（`coordinator.py:99-105` → `confirm_tool`）——委派规范只改信息质量，不动权限路径。

## 4. 实施步骤

| 批次 | 内容 | 验收 | 依赖 |
|---|---|---|---|
| **批 1** | §3.2 输出截断（第四口径常量 + 两调用点） | 大文件任务不再撑爆；三口径测试不回归 | 无 |
| **批 2** | §3.1 Condenser（含 tool_calls 折叠清洗 + notify 可见） | 12 步长任务中途出现压缩 notice、最终答案不劣化 | 无 |
| **批 3** | §3.4 委派规范（maxItems/四要素/artifact/critic 读文件） | 4 代理任务 critic 能引用子代理细节 | 无 |
| **批 4** | §3.3 渐进 schema（默认关，`lazy_groups=["mcp"]` 起步） | 首轮工具 token 下降可测 | 无 |

（四批互相独立，可按 1→2→3→4 任意穿插其他设计。）

## 5. 测试计划

- **pytest**：
  - 截断：超限加截断尾巴与「取更多」提示；PREVIEW/HISTORY/audit 三口径不受影响；
  - Condenser：阈值内不压缩；超阈折叠条数正确；**中间段含 tool_calls 时压缩后无孤儿 tool 消息**（构造 OpenAI 兼容形状断言）；压缩发 notify；`threshold=0` 禁用；**不修改入参 history**（原对象断言）；
  - decompose：>6 子任务被 schema 拒（构造非法输出走现有降级单 doer 路径）；
  - coordinator：artifact 落盘、executed 含 preview+path、critic prompt 含 path（mock 断言）；
  - schemas(groups)：core 全量 / mcp stub 形状；`tools_describe` 返回全 schema、未知名容错。
- **vitest**：tool 块 meta 附加 artifact 行渲染。
- **手动**：挂 2 个 MCP server 对比 `lazy_groups` 开/关的首 token 延迟与用量（`usage` 事件）。
