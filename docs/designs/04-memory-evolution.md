# 04 · 记忆进化：ADD-only + 有效期/溯源 + 时间打分 + 注入预算 + path 分层 + 工具化修正

> 借鉴：mem0（ADD-only、四路检索中时间信号、指代补全）、Open WebUI（path 分层、工具化记忆）、
> Graphiti（双时序失效、Episode 溯源，**不引图库**）、LobeChat（用户事实/经验分离——仅取「分类面板」思想）。
> 优先级 P2。与 05 同批（都动 `build_context`）。

## 实施状态

- **批1-4 全部完成（2026-09-29）**：
  - §3.1 迁移（facts 加 valid_until/path/origin 列，幂等 ALTER）+ `upsert` 改写为
    reconcile（等价 trigram≥0.9 只刷 ts、冲突 retire+insert、读口 active-only、`history()` 演变链）；
  - §3.2 `search` 新近度加权（`memory.recency_weight × 0.5^(age/τ)`，bm25 负值乘性加权）+
    `limit` 条数闸 + 注入 top-k/字符预算 + 行内日期；
  - §3.3 提取输入附最近对话（`_recent_dialog`）+ path 枚举归类 + 调用点传 session；
  - §3.4 新工具 `memory_search`/`memory_delete`、`memory_put` 带 path、EXECUTOR_SYSTEM 即时纠正指引；
  - §3.5 origin 溯源（extract 写 `{conv_id, turn_id}`）；
  - 配置 `MemorySection` 五字段（Settings extra=forbid 显式加）+ EditableSnapshot +
    editable_snapshot + configDefs「长期记忆」组 + config.yaml.example。
- **踩坑记录**：extract 函数内重复 `from core import config` 会把整个函数作用域的 config
  变成局部变量（session=None 分支 UnboundLocalError）——已在代码注释与本档记录。
- 测试：pytest 506 绿（记忆族新增 8：三态 reconcile/limit/新近度/预算日期/前文+path+origin/
  无 session 兼容/search+delete）、mypy 干净、vitest 248 绿、build 通过、gen:api 已重跑。

## 1. 现状（问题定位）

| # | 现状 | 位置 | 问题 |
|---|---|---|---|
| 1 | `upsert` 按 topic **覆盖**（content/source/ts 全冲掉），历史不保留 | `core/memory/facts.py:71-87` | 任务后提取可静默冲掉旧事实；`memory_put(source='voice')` 还会覆盖 `task:*` 来源 |
| 2 | 提取输入只有 `task.goal + result.summary + steps[:5]`，**无前文** | `core/memory/extract.py:50` | 「他/那里」等指代无从解析，提取失真 |
| 3 | 检索 = FTS5 trigram + bm25，**无时间衰减**；`search()` 无 LIMIT | `facts.py:102-134` | 陈旧记忆与新事实同权；多命中时注入无界 |
| 4 | 注入行只有 `topic: content`，**无 ts/source**；无 top-k、无字符预算 | `core/memory/context.py:41-55` | system prompt 可膨胀；两条读路径口径不一（`memory_get` 带来源时间） |
| 5 | 扁平 topic 列表，无层级；无有效期字段 | `facts.py:45-52` | 记忆多了不可维护；「换工作了」类事实无法标失效 |
| 6 | 实时修正仅 `memory_put`（覆盖式）+ 无删除工具 | `core/tools/memory_tools.py:10-38` | LLM 口头纠正无 `memory_delete` 手段；靠任务后提取兜底 |
| 7 | **无 memory 配置段**；顶层 `Settings` 是 `extra="forbid"` | `core/config/schema.py:427` | 新配置必须改 schema（三处同步） |

存储事实：`memory/facts.sqlite`，表 `facts(id, topic, content, source, ts)` + `facts_fts`（trigram，触发器同步），`source` 形如 `task:{id}` / `voice`，`ts` ISO8601。

## 2. 目标行为

1. **不静默覆盖**：冲突事实旧版本标失效（`valid_until`）而非删除，历史可查。
2. **检索带时间感**：近期事实加权；注入带时间与来源。
3. **注入有预算**：top-k + 字符上限，prompt 不膨胀。
4. **提取看得见前文**：喂最近对话，指代可解。
5. **可分层、可修正**：topic 支持 path 前缀；对话中即时 `memory_put/memory_delete`，不等任务结束。
6. **每条可溯源**：能指回产生它的会话/回合（Episode 溯源，不引图库）。

## 3. 设计

### 3.1 schema 迁移与 ADD-only 语义

```sql
-- ALTER 迁移（history.py 有先例）；老行全部 active、path=''
ALTER TABLE facts ADD COLUMN valid_until TEXT;      -- NULL=现行有效；ISO=已失效
ALTER TABLE facts ADD COLUMN path TEXT NOT NULL DEFAULT '';
ALTER TABLE facts ADD COLUMN origin TEXT;           -- JSON {conv_id, turn_id, msg_ts}
```

**写入规则（`upsert` 重写为 `reconcile`）**：
- **内容等价**（trigram Jaccard ≥ 0.9，复用 `tasks/store.py:45-75` 的算法）→ 仅刷新 `ts`（触达即新鲜），不产生新行。
- **内容冲突**（同 topic、相似度 < 0.9）→ 旧行 `valid_until=now`，插入新行（`source/origin` 随新写入者，不再被冲掉）。**这就是 mem0 的 ADD-only + Graphiti 的失效语义合体**。
- **显式删除**（`memory_delete` / 控制台）→ 保留现状硬删（用户意志 = 抹除，不留痕）；冲突失效是系统行为，走 `valid_until`。
- 读口：`get()` / `search()` / 注入一律 `WHERE valid_until IS NULL`；新增 `history(topic)` 供控制台「查看演变」（阶段二）。

迁移零破坏：老数据 `valid_until=NULL` 即 active，行为与现状一致。

### 3.2 检索：时间打分 + top-k + 预算

`FactStore.search(keywords, limit)` 改造：

```
bm25 分（现状）→ recency 加权：score' = score × (1 + w × 0.5 ** (age_days / τ))
  τ = memory.recency_half_life_days（默认 30）
  w = memory.recency_weight（默认 0.5，0=关闭，完全回到纯 bm25）
→ ORDER BY score' DESC LIMIT limit
```

- `context.py` 注入侧：`search(..., limit=memory.inject_top_k)`（默认 5）→ 拼接 → 超 `memory.inject_max_chars`（默认 800）按分数截断。
- 注入行格式对齐 `memory_get` 口径：`- {path}/{topic}: {content}（{ts 短格式}）`（`path` 空则省略前缀）。

### 3.3 提取：指代补全 + 分类 path

`core/memory/extract.py` 改造：
- user 消息追加前文（调用点 `pipeline.py:293-295` 处有 `session.messages`）：

```
任务：{goal}
结果：{summary}
最近对话：
- 用户：{最近 1 条 user，截 200 字}
- 助手：{最近 1 条 assistant，截 200 字}
步骤：{steps[:5]}
```

- `_FACTS_TOOL` schema 增加可选 `path` 字段（枚举：`偏好 | 习惯 | 项目 | 环境 | 其他`）与可选 `conflict_action`（`add|replace`，缺省 `add`）；`EXTRACT_FACTS_SYSTEM`（`core/prompts.py:50-51`）同步一句：「path 按语义归类；与既有记忆矛盾时由系统判定失效，不要臆删」。
- 写入走 §3.1 `reconcile`。

### 3.4 工具化实时修正

- 保留 `memory_get` / `memory_put`（`memory_put` 改走 `reconcile`——语义从「覆盖」变「失效+新增」，对 LLM 无感）。
- 新增 `@tool memory_search(query: str, path: str = "")`（risk=read）：带 id/ts/path/valid 的结构化结果。
- 新增 `@tool memory_delete(topic: str)`（risk=write，走确认链）。
- `EXECUTOR_SYSTEM`（`prompts.py:45-47`）补一句：「用户当场纠正/否定既有记忆时，立即调用 memory_put 或 memory_delete，不要等任务结束」。

### 3.5 溯源（origin）

- extract 写入时带 `origin = {conv_id: session.id, turn_id: 当前轮, msg_ts}`；`memory_put` 工具同样注入（工具已能拿 `session` 注入参数，`base.py:244-246`）。
- `memory_get` 输出补 `origin.conv_id`；控制台 `ConsoleMemoryView` 条目加「来源：会话 xxx（可跳转）」+「演变 N 条」（阶段二）。
- 不引图库：溯源就是 `source`（task:id）+ `origin`（会话坐标）两列，等价 Graphiti 的 Episode 根。

### 3.6 配置（三处同步）

```yaml
# config.yaml 新增段
memory:
  recency_half_life_days: 30    # 时间半衰期，0=禁用加权
  recency_weight: 0.5
  inject_top_k: 5
  inject_max_chars: 800
  extract_recent_messages: 2    # 提取时回看的对话条数
```

`core/config/schema.py` 新增 `MemorySection` 挂进顶层 `Settings`（`extra="forbid"` 必须显式加）→ `core/api/schemas.py` 镜像 → `configDefs.ts` 设置页「记忆」分组。

## 4. 实施步骤

| 批次 | 内容 | 验收 |
|---|---|---|
| **批 1** | §3.1 迁移 + reconcile + 读口过滤（行为对老数据零变化） | pytest 全绿；冲突写入产生失效行 |
| **批 2** | §3.2 时间打分 + top-k/预算 + 注入格式 | 多命中 prompt 长度有界；近期事实排前 |
| **批 3** | §3.3 提取指代补全 + path + §3.4 新工具/提示词 | 「上次说的那里」能落对；对话中即时纠正生效 |
| **批 4** | §3.5 origin 溯源 + 控制台展示 | 每条记忆可指回会话 |

## 5. 测试计划

- **pytest**（`tests/test_memory_*.py` 扩展）：
  - reconcile 三态：等价刷 ts / 冲突失效+插新 / 首次直插；
  - 读口只回 active；`history(topic)` 有序；
  - 时间打分：同 bm25 分新事实排前；`recency_weight=0` 退化为纯 bm25；
  - 注入预算：超 `inject_max_chars` 截断、行内含 ts；
  - 提取 prompt 含最近对话（mock LLM 断言入参）；`memory_search/memory_delete` 注册与 risk；
  - 迁移：老库 ALTER 后 active 行为不变。
- **手动**：控制台记忆页看演变链；连续两轮矛盾指令后 `memory_get` 返回新事实 + 旧的进 history。
