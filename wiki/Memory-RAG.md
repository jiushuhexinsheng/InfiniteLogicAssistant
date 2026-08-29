# 记忆与 RAG

## 三级记忆

| 级 | 存什么 | 存哪 | 何时写 |
|----|--------|------|--------|
| 短期 | 当前会话消息/工具结果 | 内存 `Session.messages`（前端同时 localStorage 持久化） | 实时 |
| 长期·事实 | 用户偏好、常用路径、信任关系 | `memory/facts.sqlite`（**FTS5 全文检索**） | 任务结束后 LLM 异步提取 |
| 长期·检索 | 环境/文档分块索引 | `rag/index.db` | 启动按需 / 手动重建 |

## 长期记忆（facts.sqlite）

- 表：`facts(topic, content, source, ts)`，按 topic upsert 去重。
- **FTS5 索引**（`tokenize='trigram'`，适配中文）：触发器同步增删改，`bm25()` 排序。
  - ≥3 字符关键词走全文检索；<3 字符回退子串扫描。
  - 迁移：首次打开自动建 `facts_fts` 虚拟表并回填。
- 接口：`memory_get` / `memory_put` 工具；`GET/DELETE /api/memory` 浏览/删除。

## RAG

- 索引源：`environment.md` + `docs/`（`core/rag/__init__.py` 的 `DEFAULT_SOURCES`）。
- 分块：按 `#` 标题切块（≤800 字），入 `rag/index.db` 的 `chunks` 表。
- 检索：**BM25** 打分（纯 Python，无外部依赖），中文按字符二元组近似分词。
- 注入：执行器构建上下文时把 RAG 片段 + 相关记忆拼进系统提示（`core/memory/context.py::build_context`，失败不影响执行）。
- 重建：`server` 启动时按需（`index.db` 缺失或源更新）；`rag.auto_index` 可关闭。

## 环境感知

`core/detection/environment.py` 采集系统信息写入 `environment.md`（人可读），
作为 RAG 默认源与规划上下文注入，让工具参数贴合真实系统。
