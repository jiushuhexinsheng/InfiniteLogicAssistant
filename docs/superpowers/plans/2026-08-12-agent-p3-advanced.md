# 语音全控智能体 P3 多智能体 + 定时 + GUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补上多智能体协作（协调者+子代理）、定时任务（cron 式 + 语音注册）、GUI 自动化（pyautogui/win32），达成"复杂任务自动拆解多步执行、每天九点查天气并播报、语音控制打开/操作应用"。

**Architecture:** `core/agent/` 协调者拆解任务 → 分派子代理（planner/doer/searcher/critic），独立子任务 asyncio 并发；`core/scheduler/` cron 注册到点推入编排管线；`core/execution/gui.py` 鼠标键盘窗口控制工具。前端新增 定时 视图。

**Tech Stack:** Python 3.14、`asyncio`、`croniter`（可选）或自写 cron 匹配、`pyautogui` + `pygetwindow`（Windows）、`web` Vue。

## Global Constraints

- 子代理共享同一 `TOOLS`/`RAG`/`Memory`/`CancellationToken`；协调者汇聚结果、critic 把关可打回。
- 并发子任务数量上限（默认 4），且每个子任务可独立中止。
- 定时任务到点触发复用完整编排管线（含澄清/确认——无人确认时自动降级：只读自动、高风险跳过并通知）。
- GUI 自动化高风险：点击/键盘/窗口操作默认 `confirm`；仅 `gui_activate`（打开已装应用）可视配置免确认。
- 依赖新增补 `scripts/libs` 离线 wheel。

---

### Task 1: 子代理基座

**Files:**
- Create: `core/agent/base.py`
- Create: `tests/test_agent_base.py`

**Interfaces:**
- Produces:
  - `class SubAgent: name:str; role_prompt:str; async def run(goal:str, context:str, tools, cancel) -> SubAgentResult`
  - `@dataclass SubAgentResult: status:str; output:str; used_tools:list[str]`
  - `async def run_subagent(role_prompt, goal, context, cancel) -> SubAgentResult` — 一次 LLM 循环（ReAct），工具经 `TOOLS.acall`，可取消。
- [ ] **Step 1: 写失败测试**（假 LLM 脚本：run_subagent 调工具→产出结果；cancel 中止）
- [ ] **Step 2-4: 失败→实现→通过**
- [ ] **Step 5: 提交** `feat(P3): 子代理基座 run_subagent`

### Task 2: 协调者 coordinator（拆解/分派/合并）

**Files:**
- Create: `core/agent/coordinator.py`
- Create: `tests/test_coordinator.py`

**Interfaces:**
- Consumes: `run_subagent`、`Task`、`CancellationToken`。
- Produces:
  - `async def run_coordinator(task: Task, channel, cancel) -> dict` — LLM 把任务拆为子任务列表（结构化输出 `[{goal, agent_type, independent}]`）→ 独立子任务并发（上限 4）→ 汇总结果交给 critic。
  - 子代理类型注册表：`planner/doer/searcher/critic` 对应角色提示词（`prompts/agent_*.md`）。
- [ ] **Step 1: 写失败测试**（拆解两个独立子任务→并发→合并；critic 打回重做一次）
- [ ] **Step 2-4: 失败→实现→通过**
- [ ] **Step 5: 提交** `feat(P3): 多智能体协调者（拆解/并发/汇聚）`

### Task 3: executor 接入多智能体

**Files:**
- Modify: `core/orchestrator/executor.py`
- Create: `tests/test_executor_agent.py`

**Interfaces:**
- Produces: executor 内新增策略：`complex` 任务（子任务数>1）转 `run_coordinator`；简单任务保持单 agent ReAct。
- [ ] **Step 1: 写失败测试**（复杂任务走 coordinator 分支；简单任务走原路径）
- [ ] **Step 2-4: 失败→实现→通过**
- [ ] **Step 5: 提交** `feat(P3): executor 复杂任务转多智能体`

### Task 4: 定时任务 scheduler

**Files:**
- Create: `core/scheduler/scheduler.py`
- Create: `core/tools/schedule_tools.py`
- Create: `tests/test_scheduler.py`

**Interfaces:**
- Produces:
  - `class Scheduler: async def start(); async def stop(); async def add(schedule: Schedule) -> None; async def remove(id) -> None`
  - `@dataclass Schedule: id; cron:str; prompt:str; enabled:bool`
  - `@tool("注册定时任务", risk="write") register_schedule(cron, prompt)`、`@tool("列出定时任务", risk="read") list_schedules()`、`@tool("取消定时任务", risk="write") remove_schedule(id)`
  - 到点触发：构造 `Task(prompt)` 推入编排；无人值守降级（见 Global Constraints）。
- [ ] **Step 1: 写失败测试**（cron 匹配器下一个触发时间；add/remove；到点回调推任务）
- [ ] **Step 2-4: 失败→实现→通过**
- [ ] **Step 5: 提交** `feat(P3): 定时任务 scheduler + 语音注册工具`

### Task 5: GUI 自动化

**Files:**
- Create: `core/execution/gui.py`
- Create: `core/tools/gui_tools.py`
- Create: `tests/test_gui.py`（不触碰真实屏幕，只测参数校验与 launch 封装）

**Interfaces:**
- Produces:
  - `async def gui_activate(app_name:str) -> str`（`shutil.which`/`start` 打开已装应用）、`async def gui_click(x:int, y:int) -> str`、`async def gui_type(text:str) -> str`、`async def gui_screenshot(path:Path) -> str`、`async def list_windows() -> str`
  - 工具：`gui_activate`（默认 read 免确认）/ `gui_click` / `gui_type` / `gui_screenshot` / `list_windows`（后四者 risk="exec"）。
- [ ] **Step 1: 写失败测试**（list_windows 返回文本；参数校验；`gui_activate("notepad")` 封装调用）
- [ ] **Step 2-4: 失败→实现→通过**
- [ ] **Step 5: 提交** `feat(P3): GUI 自动化工具`

### Task 6: 前端定时/多智能体视图 + 收尾

**Files:**
- Modify: `web/src/views/ConsolePage.vue`（新增 定时 Tab）
- Create: `web/src/components/console/ConsoleScheduleView.vue`、`ConsoleAgentView.vue`
- Modify: `web/src/api.ts`（schedule 端点 + 子代理/任务流事件）

**Interfaces:**
- Produces: `GET/POST/DELETE /api/schedules`；任务视图展示协调者拆解的子任务流。
- [ ] **Step 1: 后端 schedule 端点 + 测试**
- [ ] **Step 2: 前端定时 Tab**（增删列表 + 语音注册入口）
- [ ] **Step 3: `npm run build` 通过**
- [ ] **Step 4: 手动冒烟**（"每天九点查天气"注册 → 手动触发一次 → 播报；语音"打开记事本"→ GUI 激活）
- [ ] **Step 5: 提交** `feat(P3): 定时/多智能体视图 + 收尾`

---

## P3 验收清单

- [ ] 复杂任务（如"整理下载文件夹并按类型归档"）自动拆解多步、独立子任务并发、critic 把关。
- [ ] 语音注册定时任务，到点自动执行（无人值守降级规则生效）。
- [ ] 语音"打开记事本"等 GUI 控制可用；高影响 GUI 操作过确认。
- [ ] 全部 pytest 通过；`npm run build` 通过。

## P3 审查清单

- [ ] 子任务并发上限与各自可中止；结果汇聚无丢失。
- [ ] 定时任务无人确认时只读自动、高风险跳过并通知（不静默失败）。
- [ ] GUI 工具 risk 分类正确；截图等不外发（本地保存）。
- [ ] 与 P0-P2 全部功能联动无回归（pytest + 冒烟）。
