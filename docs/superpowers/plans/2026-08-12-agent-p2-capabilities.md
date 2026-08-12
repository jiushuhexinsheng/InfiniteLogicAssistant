# 语音全控智能体 P2 能力扩展 MCP + Skills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 P0/P1 地基扩展外部能力：MCP 客户端（桥接任意 MCP server 的工具）与 Skills 系统（可复用能力包，热加载），让"接一个 MCP server 并语音调用其工具"、"执行我 skill 里的 xxx"跑通。

**Architecture:** `core/mcp/` 客户端连 MCP server，工具经 `tools/mcp_bridge.py` 动态注册进 `TOOLS`（对编排层透明）；`core/skills/` 定义 `skills/*.yaml` 能力包 + 加载器（监听目录热加载）+ 执行器（把步骤模板展开为工具调用序列）。

**Tech Stack:** Python 3.14、MCP SDK（`mcp` 包，需补离线 wheel）、PyYAML（已有）、`web` Vue。

## Global Constraints

- MCP 工具与本地工具对编排层**完全透明**（统一 `TOOLS` 注册中心）。
- MCP 工具风险级：工具 schema 无 risk 时默认 `exec`（需 confirm），MCP server 声明只读者可为 `read`。
- Skill 定义 `skills/*.yaml`，格式固定；改动热生效（loader 监听 mtime）。
- 依赖新增补 `scripts/libs` 离线 wheel。

---

### Task 1: MCP 客户端

**Files:**
- Create: `core/mcp/client.py`
- Create: `tests/test_mcp_client.py`

**Interfaces:**
- Produces:
  - `class McpConnection: async def connect(server: McpServerCfg); async def list_tools() -> list[McpTool]; async def call_tool(name: str, args: dict) -> str; async def close()`
  - `@dataclass McpServerCfg: name: str; command: str; args: list[str]`
  - `McpTool: {name, description, inputSchema}`
- [ ] **Step 1: 写失败测试**（用官方 `mcp` SDK 连接一个 echo server 或 mock，断言 list_tools/call_tool）
- [ ] **Step 2: 运行确认失败**；**Step 3: 实现**（MCP stdio transport + `ClientSession`）；**Step 4: 验证通过**；**Step 5: 提交** `feat(P2): MCP 客户端连接与工具枚举`

### Task 2: MCP 桥（动态注册到 TOOLS）

**Files:**
- Create: `core/tools/mcp_bridge.py`
- Create: `tests/test_mcp_bridge.py`

**Interfaces:**
- Consumes: `McpConnection`、`TOOLS`（`_ToolRegistry.register`）。
- Produces: `async def register_mcp_tools(conn: McpConnection) -> None` — 把 MCP 工具包装为 `@tool` 等价物注册进 TOOLS（name 加前缀 `mcp_<server>_<tool>`），`acall` 转发 `conn.call_tool`；`async def unregister_mcp_tools(server_name)`。
- [ ] **Step 1: 写失败测试**（mock conn 的 list_tools 两个工具 → TOOLS.has 命中前缀名；call 转发）
- [ ] **Step 2-4: 失败→实现→通过**
- [ ] **Step 5: 提交** `feat(P2): MCP 工具动态注册进 TOOLS`

### Task 3: MCP 配置与生命周期接入

**Files:**
- Modify: `core/config.py`（新增 `mcp.servers[]` 段）
- Modify: `core/execution/envprobe.py`（探测已装 MCP server）
- Modify: `server.py`（启动时连 MCP，`GET /api/tools` 含 MCP 工具）
- Create: `tests/test_mcp_integration.py`

**Interfaces:**
- Produces: `core/mcp/manager.py`：`class McpManager: async def start_all(); async def stop_all(); list_connections()`。
- [ ] **Step 1: 写失败测试**（config 解析 mcp.servers；manager 启动/关闭）
- [ ] **Step 2-4: 失败→实现→通过**
- [ ] **Step 5: 提交** `feat(P2): MCP 配置、生命周期与 /api/tools 集成`

### Task 4: Skills 定义与热加载

**Files:**
- Create: `core/skills/loader.py`
- Create: `skills/example.yaml`（示例）
- Create: `tests/test_skills_loader.py`

**Interfaces:**
- Produces:
  - `Skill` 结构（解析 `skills/*.yaml`）：`{name, description, requires[], steps[{tool, args_template, note}], validate, dangerous}`
  - `async def load_skills() -> dict[str, Skill]` + 监听 mtime 增量重载。
- [ ] **Step 1: 写失败测试**（解析 example.yaml；改动文件后重载生效）
- [ ] **Step 2-4: 失败→实现→通过**
- [ ] **Step 5: 提交** `feat(P2): Skills 定义与热加载`

### Task 5: Skill 执行器

**Files:**
- Create: `core/skills/executor.py`
- Create: `core/tools/skill_tools.py`
- Create: `tests/test_skills_executor.py`

**Interfaces:**
- Consumes: `Skill`、`TOOLS`、`CancellationToken`、`OperatorChannel`。
- Produces:
  - `async def run_skill(skill: Skill, params: dict, channel, cancel) -> str` — 依 steps 顺序展开：`args_template` 填参 → `TOOLS.acall` → 结果拼接；`validate` 校验步骤间不变量；`dangerous` 需 `confirm_if_needed`。
  - `@tool("列出可用技能", risk="read") list_skills()`、`@tool("执行技能", risk="exec") run_skill_tool(name, params)`。
- [ ] **Step 1: 写失败测试**（两步 skill 展开执行；dangerous 触发 confirm；参数模板填充）
- [ ] **Step 2-4: 失败→实现→通过**
- [ ] **Step 5: 提交** `feat(P2): Skill 执行器 + 语音可调用的 skill 工具`

---

## P2 验收清单

- [ ] 配置一个 MCP server（如 filesystem）→ 启动自动连上 → `/api/tools` 出现 `mcp_*` 工具 → 语音调用成功。
- [ ] 语音"执行我 skill 里的 xxx"：命中 skill、填参、展开执行、dangerous 先确认。
- [ ] skill 文件改动热生效（不重启）。
- [ ] 全部 pytest 通过；`npm run build` 通过。

## P2 审查清单

- [ ] MCP 工具名带 server 前缀防冲突；连接/关闭生命周期无泄漏。
- [ ] Skill 参数模板填充类型一致；dangerous 一律走 confirm。
- [ ] 新依赖（mcp SDK 等）已补离线 wheel。
- [ ] MCP/Skill 对编排层透明（executor 无感知差异）。
