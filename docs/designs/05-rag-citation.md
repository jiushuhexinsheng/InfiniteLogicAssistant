# 05 · RAG 引用溯源（citation 块）+ 可选 rerank

> 借鉴：AnythingLLM（回答标注来源 chunk）、Open WebUI / Dify（检索多策略 + rerank 分档）。
> 优先级 P2。与 04 同批（共用 `build_context` 改动）。**不引向量库/新重模型依赖**，
> rerank 默认关闭、可选 LLM 打分档——保持项目轻量原则。

## 实施状态

- **批1-2 已完成（2026-09-29）；批3（chips 跳转文件）未做（可选）**：
  - §3.1 `build_context_with_sources` 返回 (文本, hits)；RAG 段改编号注入
    `[n] 标题 (path)`（`retriever.format_hits`，`rag_context` 同步换格式）；
    `RAG_CITE_NOTE` 仅在有命中时附进 system（executor 组装）；
  - §3.2 后端 `BLOCK_SOURCES`（meta: 折叠+不播报，text 投影天然跳过）+ executor 发
    `BlockEvent` 直通；前端 `SourcesBlock.vue`（默认折叠 chips + 展开 path/分数）+
    registry 注册（summarize `📄 N 个来源`、speak null）；
  - §3.3 `RagSection` 加 `rerank/rerank_candidates/rerank_top_k`（默认 none）+
    `retriever.rerank`（单次 LLM 闭集打分、temperature=0、失败回退 BM25 序 + 审计
    `rag-rerank-fallback`、候选 ≤ top_k 不调用）+ 配置三处同步 + gen:api。
- 与设计偏差：`build_context` 保持 `-> str`（协调者等文本调用方零改动），tuple 版为
  新函数 `build_context_with_sources`（executor 单点消费）。
- 测试：pytest 506 绿（新增 4：编号格式/重排成功/失败回退/sources 块+尾注进 system）、
  vitest 248 绿（SourcesBlock 3 例）、mypy 干净、build 通过。

## 1. 现状（问题定位）

| # | 现状 | 位置 | 问题 |
|---|---|---|---|
| 1 | 注入格式 = `[section 或 path]\n{text}` 一行文本头，**score 不进 prompt、无引用编号** | `core/rag/retriever.py:107-116` | LLM 无法规范引用；用户无法核对 |
| 2 | `retrieve()` 返回结构化 `{path, section, text, score}` 但**只被 `rag_context` 消费**，命中不外传前端 | `retriever.py:55-86` | 前端零来源信息 |
| 3 | 单阶段纯 BM25（k1=1.5 b=0.75），**无 rerank** | `retriever.py:16-51` | 头部命中质量受词面匹配限制 |
| 4 | 无 citation 相关块类型；块协议已支持 `ext:*` 与 `block` 事件直通 | `core/orchestrator/blocks.py`、`web/src/blocks/normalize.ts:171-185` | ✅ 扩展通道现成 |
| 5 | `RagSection` 仅 `auto_index` 一个字段 | `core/config/schema.py:394-402` | 加配置需三处同步 |

## 2. 目标行为

1. 每回合命中来源以**结构化块**呈现给前端（可折叠「来源」列表：path/section/分数）。
2. LLM prompt 内命中带**编号 [n]**，正文引用时标注 `[n]`（软约束，chips 是权威展示）。
3. 可选 rerank 档位（`none` 默认 / `llm`），失败静默回退 BM25 序。
4. 全程 additive：事件契约只增块类型，不改既有语义。

## 3. 设计

### 3.1 结构化命中贯穿（后端）

`core/memory/context.py` 的 `build_context(query)` 返回值从 `str` 改为 `tuple[str, list[dict]]`（文本, hits）：

```python
hits = retrieve(query, top_k=rag.rerank_top_k)      # 结构化（含 score）
text = "\n\n".join(f"[{i+1}] {h['section'] or h['path']} ({h['path']})\n{h['text']}"
                   for i, h in enumerate(hits))     # 编号注入
```

- 调用方两处适配：`executor.py:74-90`（单代理）与 `coordinator.py:108-112`（多代理）——hits 只在**主执行路径**（executor）向前端发块；coordinator 仅用 text（子代理上下文不重复发来源块）。
- prompt 尾注（放 `UNTRUSTED_DATA_NOTE` 旁，`prompts.py:56-57`）：「引用上述资料时标注来源编号，如 [1]；不确定来源就不要标注」。

### 3.2 来源块下发（SSE → 块协议）

复用现有 `BlockEvent` 直通通道（`events.py:162-173`、`normalize.ts:171-185`），不新增事件类型：

- executor 在 `build_context` 得到 hits 且非空 → `await events.put(BlockEvent(block={...}).emit())`：

```json
{ "v":1, "type":"sources", "id":"...", "ts":"...",
  "payload": { "items": [ {"n":1, "path":"docs/x.md", "section":"配置", "score":3.412} ] },
  "meta": { "collapsed": true } }
```

- `blocks.py` 的 `block_from_dict`/白名单允许 `sources` 类型（后端块模型加一个成员，或走既有 `ext:` 兜底——**选显式注册**，前后端语义一致）。
- 前端：
  - `registry.ts` 注册 `registerBlock('sources', { component: SourcesBlock, summarize: '📄 N 个来源', speak: null })`；
  - `SourcesBlock.vue`：可折叠 chips（path + section 徽章 + score 两位小数），点击复制路径（阶段二：控制台内跳转文件查看——依赖现有文件浏览能力，没有则只复制）；
  - 位置：normalize 中 sources 块按到达顺序插入（通常在正文前），渲染在消息流内即可，**不进 text 投影**（与 thinking 同规则：`text_projection` 跳过）。
- 与 04 注入格式的衔接：`【相关文档/环境】` 段采用同一编号文本（04 只改记忆段格式，不冲突）。

### 3.3 可选 rerank（两档，不引重依赖）

`RagSection` 扩展：

```yaml
rag:
  auto_index: true
  rerank: none          # none | llm
  rerank_candidates: 12 # BM25 粗排候选数
  rerank_top_k: 5       # 精排后注入数（与现状 top_k=5 一致）
```

**`llm` 档管线**（`core/rag/retriever.py` 新增 `rerank(query, hits)`）：
1. BM25 取 `rerank_candidates`（12）条；
2. 单次 LLM 调用打分：把编号+「标题/正文截 300 字」列表给模型，闭集工具返回 `{scores: [{n, score 0-10}]}`，temperature=0（复用 `agent.structured_temperature` 或 0）；
3. 按分数重排取 `rerank_top_k`；
4. **任何失败（超时/解析失败/模型不可用）→ 静默回退 BM25 序**，audit 记 `rag-rerank-fallback`；
5. 成本闸门：`hits ≤ rerank_top_k` 时跳过（无需精排）。

**明确不做**（记录为备选）：cross-encoder / embedding rerank（需 sentence-transformers 或 embedding 端点，违背轻量原则；若未来 `llm_client` 加 embedding 协议再评估）。

### 3.4 前端文案与统计（轻量）

- summary 卡不重复列来源（sources 块自展示）；
- `usage` 事件已有 token 统计，rerank 的那次 LLM 调用单独记 audit（`rag-rerank n=12`），**不并入**会话 usage（避免污染成本视图），README 成本实测节补一行口径。

## 4. 实施步骤

| 批次 | 内容 | 验收 |
|---|---|---|
| **批 1** | §3.1 编号注入 + §3.2 sources 块（后端模型/事件 + 前端注册/渲染） | 回合内出现可折叠来源 chips；老前端收到未知块走 UnknownBlock 不炸 |
| **批 2** | §3.3 rerank `llm` 档 + 配置三处同步 + 回退审计 | 开关开启可见顺序变化；关掉=现状零成本 |
| **批 3**（可选） | chips 点击跳转/复制增强、控制台来源视图 | 手动验收 |

## 5. 测试计划

- **pytest**：
  - `build_context` 返回 (text, hits)，text 首行含 `[1]`；hits 空 → 不发 BlockEvent；
  - executor 发出的 block 事件 `type='sources'`、不进 `text_projection`；
  - rerank：正常重排、`hits≤top_k` 跳过、LLM 失败回退 BM25 序（mock 抛错/坏 JSON）、audit 落 `rag-rerank-fallback`；
  - 配置 `rerank` 枚举校验（非法值启动报错）。
- **vitest**：`registry.spec` sources 注册/summarize/speak=null；`normalize.spec` sources 块直通与投影跳过；`SourcesBlock.spec` 折叠与 chips 渲染。
- **手动**：任务模式问一个知识库问题 → 正文带 [1] 引用、来源 chips 与注入一致。
