# 语音全控智能体 P1 记忆 + RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 P0 地基补上持久记忆（三级：短期/长期事实/向量）与 RAG 检索，实现跨会话记住用户偏好，"按上次的方式查天气"这类指令可直接执行。

**Architecture:** `core/memory/` 三层存储（会话内存 / facts.sqlite / 向量索引）+ `core/rag/`（索引 environment.md 与文档目录，检索注入上下文）；任务结束后 LLM 摘要提取事实写长期记忆；记忆工具注册进 `TOOLS` 供编排层调用。

**Tech Stack:** Python 3.14、sqlite3（stdlib）、可选 `numpy`（向量余弦，可先退化为关键词）、`web` Vue 记忆浏览。

## Global Constraints

- 复用 P0 的 `@tool`、`OperatorChannel`、`Task`、`CancellationToken`。
- 记忆读写在编排层生命周期内由 Session 注入；不阻塞主执行（异步落库）。
- 向量检索先以 TF-IDF/关键词起步，可后换向量库；RAG 结果限制 top-k=5。
- 事实存储去重（同主题合并）；所有记忆文件在 `memory/`（gitignore 保留样例）。

---

### Task 1: 长期事实记忆 facts.sqlite

**Files:**
- Create: `core/memory/facts.py`
- Create: `tests/test_memory_facts.py`

**Interfaces:**
- Produces:
  - `class FactStore: __init__(path=memory/facts.sqlite); async def upsert(topic:str, content:str, source:str)->None; async def get(topic:str)->list[dict]; async def search(keywords:list[str])->list[dict]`
- [ ] **Step 1: 写失败测试**（upsert 后 get 返回；同主题 upsert 合并不重复；search 按关键词命中）
- [ ] **Step 2: 运行确认失败**；**Step 3: 实现**（sqlite 表 `facts(id, topic, content, source, ts)`，`upsert` 按 topic 合并）；**Step 4: 验证通过**；**Step 5: 提交** `feat(P1): 长期事实记忆 facts.sqlite`

### Task 2: 短期会话记忆接入

**Files:**
- Modify: `core/orchestrator/session.py`
- Create: `tests/test_session_memory.py`

**Interfaces:**
- Produces: `Session.memory: list[dict]`（消息+工具结果），`Session.summary()`（供上下文注入）。
- [ ] **Step 1: 写失败测试**（消息累积 + summary 截断到 N 条）
- [ ] **Step 2-4: 失败→实现→通过**
- [ ] **Step 5: 提交** `feat(P1): 短期会话记忆与摘要`

### Task 3: 任务后事实提取（LLM 摘要写记忆）

**Files:**
- Create: `core/memory/extract.py`
- Create: `tests/test_memory_extract.py`

**Interfaces:**
- Consumes: `FactStore`、`get_llm_client`、`Task`。
- Produces: `async def extract_and_store(task:Task, result:dict, channel:OperatorChannel)->None` — 让 LLM 结构化输出 `{facts:[{topic,content}]}`，写入 FactStore；异步不阻塞返回。
- [ ] **Step 1: 写失败测试**（假 LLM 输出 facts → store 落库）
- [ ] **Step 2-4: 失败→实现→通过**
- [ ] **Step 5: 提交** `feat(P1): 任务后 LLM 提取长期事实`

### Task 4: RAG 索引与检索

**Files:**
- Create: `core/rag/indexer.py`、`core/rag/retriever.py`
- Create: `tests/test_rag.py`

**Interfaces:**
- Produces:
  - `async def index_sources(sources: list[Path]) -> None` — 切块（按段落/标题），写入 `rag/index.db`（sqlite：`chunks(id, path, section, text)`）。
  - `async def retrieve(query: str, top_k: int = 5) -> list[dict]` — 关键词+TF-IDF 打分，返回 `[{path, section, text}]`。
  - `async def rag_context(query) -> str` — 检索 top-k 拼接为上下文文本。
- [ ] **Step 1: 写失败测试**（index environment.md 后，`retrieve("python 版本")` 命中对应段）
- [ ] **Step 2-4: 失败→实现→通过**
- [ ] **Step 5: 提交** `feat(P1): RAG 索引与检索`

### Task 5: RAG 注入编排上下文

**Files:**
- Modify: `core/orchestrator/intent.py`、`core/orchestrator/task.py`、`core/orchestrator/executor.py`
- Create: `tests/test_rag_inject.py`

**Interfaces:**
- Produces: `async def build_context(session, query) -> str` — `rag_context` + 相关 `FactStore.search` 合并注入系统提示。
- [ ] **Step 1: 写失败测试**（executor 收到含 RAG 上下文的历史；假 LLM 断言提示中含检索片段）
- [ ] **Step 2-4: 失败→实现→通过**
- [ ] **Step 5: 提交** `feat(P1): RAG 与记忆上下文注入编排`

### Task 6: memory 工具注册 + 前端记忆浏览

**Files:**
- Create: `core/tools/memory_tools.py`
- Modify: `web/src/views/ConsolePage.vue`（新增记忆 Tab）
- Create: `web/src/components/console/ConsoleMemoryView.vue`

**Interfaces:**
- Produces:
  - `@tool("读取长期记忆", risk="read") async def memory_get(topic:str)->str`
  - `@tool("写入长期记忆", risk="write") async def memory_put(topic:str, content:str)->str`
  - `GET /api/memory` → FactStore 全部条目（供前端浏览/撤销）。
- [ ] **Step 1: 后端工具 + 端点 + 测试**
- [ ] **Step 2: 前端记忆 Tab**（列表 + 删除单条）
- [ ] **Step 3: `npm run build` 通过**
- [ ] **Step 4: 手动冒烟**（说"以后默认用中文简洁汇报"→ 记忆落库 → 新会话执行时自动遵守）
- [ ] **Step 5: 提交** `feat(P1): memory 工具 + 前端记忆浏览`

---

## P1 验收清单

- [ ] 跨会话记住偏好：本会话写入的记忆，新会话启动时自动注入并影响执行。
- [ ] "按上次的方式查天气"：能从记忆/RAG 找到上次的方式并直接执行。
- [ ] 任务结束后事实自动提取入 facts.sqlite；同主题不重复。
- [ ] `/api/memory` 可浏览与删除。
- [ ] 全部 pytest 通过；`npm run build` 通过。

## P1 审查清单

- [ ] 记忆写入不阻塞主流程；读取在上下文注入前完成。
- [ ] 事实去重合并正确；向量/关键词检索结果 top-k 限制。
- [ ] memory 工具 `risk` 分类正确（get=read，put=write 走 confirm）。
- [ ] 前端删除记忆后后端同步删除；SSE/API 一致。
