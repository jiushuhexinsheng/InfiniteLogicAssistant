# 语音全控智能体 P0 地基 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭建语音全控智能体的地基：环境感知 + 执行层（shell/py/文件）+ 基础工具集 + 自研编排闭环（会话/意图/任务/澄清/确认/执行/停止）+ 后端集成与桌面语音监听接入，使"语音把桌面 xx.txt 复制到下载 + 停止可中断"跑通全链路。

**Architecture:** 分层：交互层(语音/Web) → 编排层(orchestrator) → 能力层(tools) → 执行层(execution)。编排自研轻量，复用现有 `core/llm`、`core/tools/base.py`、`core/config.py`、`server.py`、Vue 控制台。`CancellationToken` 横切所有执行路径实现可中止。

**Tech Stack:** Python 3.14、FastAPI + httpx、pytest、Vue3 + TS；新增依赖按需补入 `scripts/libs` 离线 wheel。

## Global Constraints

- Python 3.14+；所有后端代码沿用现有 `core/` 结构与 docstring 风格（中文）。
- 复用不重写：`core/llm/stream.py`、`core/llm/client.py`、`core/tools/base.py`(`@tool`)、`core/config.py`、`server.py`、`web`。
- **无沙箱**：不设安全区；高风险操作（写/删除/执行任意命令/网络外发）一律走 `confirm.py` 人类确认。
- `CancellationToken` 必须贯穿 执行层每个工具调用 与 子进程（kill 进程树兜底）。
- TDD：每个任务先写失败测试，再实现，再验证通过，再提交。
- 新增依赖必须补 `scripts/libs/` 离线 wheel（`install_deps.bat` 用 `--find-links`）。
- 端点/SSE 向后兼容：现有 `/api/ai/chat` 事件不变，只新增事件类型。

---

### Task 1: 环境感知 envprobe → environment.md

**Files:**
- Create: `core/execution/__init__.py`
- Create: `core/execution/envprobe.py`
- Create: `tests/test_envprobe.py`
- Test: `tests/test_envprobe.py`

**Interfaces:**
- Produces:
  - `async def probe() -> dict[str, Any]` — 收集系统信息，键含 `os/hostname/arch/cpu/memory_gb/disk_gb/path/shell/python/software[]/net_ok`。
  - `async def write_environment_md(data: dict, path: Path = ROOT/"environment.md") -> Path` — 把 data 写成结构化 Markdown（按键分组小节，含命令式原文）。
  - `async def env_probe(update: bool = False) -> str` — `@tool(..., risk='read')` 包装：读已存在 md 或重新 probe，返回 md 文本。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_envprobe.py
import asyncio
from pathlib import Path
import pytest
from core.execution.envprobe import probe, write_environment_md

@pytest.mark.asyncio
async def test_probe_collects_expected_keys(tmp_path):
    data = await probe()
    for k in ("os", "hostname", "arch", "cpu", "memory_gb", "path", "shell", "python"):
        assert k in data and data[k]

@pytest.mark.asyncio
async def test_write_environment_md_creates_file(tmp_path):
    md = await write_environment_md({"os": "Windows 11", "path": "C:\\x"}, tmp_path / "environment.md")
    text = md.read_text(encoding="utf-8")
    assert "## 系统" in text and "Windows 11" in text
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_envprobe.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 `core/execution/envprobe.py`**

用 `platform`、`os.environ`、`shutil.which`、`psutil`(若已装；否则用 `os.cpu_count`/`shutil.disk_usage`/`platform` 组合) 采集；`write_environment_md` 按固定模板渲染 Markdown 并落盘 `environment.md`（项目根，gitignore 之外保留提交）。

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/test_envprobe.py -v`
Expected: PASS

- [ ] **Step 5: 生成真实 environment.md 并提交**

Run: `py -3.14 -c "import asyncio; from core.execution.envprobe import probe, write_environment_md; d=asyncio.run(probe()); asyncio.run(write_environment_md(d))"`；确认根目录生成 `environment.md`。
Expected: `environment.md` 存在且含 OS/路径/命令等真实信息

```bash
git add core/execution/ tests/test_envprobe.py environment.md
git commit -m "feat(P0): 环境感知 envprobe → environment.md"
```

---

### Task 2: 执行层 shell.py（进程控制）

**Files:**
- Create: `core/execution/shell.py`
- Create: `tests/test_shell.py`

**Interfaces:**
- Consumes: `core/orchestrator/control.py` 的 `CancellationToken`（本任务可先用 Task 10 的签名桩；若顺序执行则 Task 10 定义后回填，二者签名需一致）。
- Produces:
  - `@dataclass class ShellResult: returncode:int; stdout:str; stderr:str; duration:float`
  - `async def run_shell(command: str, *, cwd: str|None=None, timeout: float=30, cancel: Any|None=None) -> ShellResult`
  - `def kill_tree(pid: int) -> None` — Windows 用 `taskkill /T /F /PID`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_shell.py
import pytest
from core.execution.shell import run_shell, kill_tree

@pytest.mark.asyncio
async def test_run_shell_echo():
    r = await run_shell("echo hello")
    assert r.returncode == 0 and "hello" in r.stdout

@pytest.mark.asyncio
async def test_run_shell_timeout():
    with pytest.raises(TimeoutError):
        await run_shell("ping -n 10 127.0.0.1", timeout=1)
```

- [ ] **Step 2: 运行确认失败** → `pytest tests/test_shell.py -v`，Expected FAIL
- [ ] **Step 3: 实现** 用 `asyncio.create_subprocess_shell` + `asyncio.wait_for`；超时或 cancel 时 `kill_tree` 后抛 `TimeoutError`/`CancelledError`；流式读 stdout/stderr 合并（分通道）。

- [ ] **Step 4: 运行确认通过** → `pytest tests/test_shell.py -v`，Expected PASS
- [ ] **Step 5: 提交** → `git commit -m "feat(P0): shell 进程控制 run_shell/kill_tree"`

---

### Task 3: 执行层 python.py

**Files:**
- Create: `core/execution/python.py`
- Create: `tests/test_python.py`

**Interfaces:**
- Consumes: `run_shell`。
- Produces: `async def run_python(code: str | Path, *, cwd=None, timeout=60, cancel=None) -> ShellResult`（写临时 .py 或直接 `python -c`，独立子进程，避免污染宿主）。

- [ ] **Step 1: 写失败测试**

```python
@pytest.mark.asyncio
async def test_run_python_prints():
    r = await run_python("print(1 + 1)")
    assert r.returncode == 0 and "2" in r.stdout
```

- [ ] **Step 2: 运行确认失败**；**Step 3: 实现**（`sys.executable` + 临时文件 + run_shell）；**Step 4: 验证通过**；**Step 5: 提交** `feat(P0): python 脚本执行 run_python`

---

### Task 4: 执行层 fs.py（读写所有通用格式）

**Files:**
- Create: `core/execution/fs.py`
- Create: `tests/test_fs.py`

**Interfaces:**
- Produces:
  - `async def read_doc(path: Path) -> Any` — 按扩展名分发：`.json/.yaml/.yml/.toml/.csv/.md/.txt/.xlsx/.sqlite/.ini/.env`。
  - `async def write_doc(path: Path, data: Any) -> None` — 对应格式写回（xlsx 用 `openpyxl`，sqlite 用 `sqlite3`，csv 用 `csv`，ini 用 `configparser`）。
  - `async def list_dir(path: Path) -> list[dict]`、`async def stat_path(path: Path) -> dict`。

- [ ] **Step 1: 写失败测试**

```python
@pytest.mark.asyncio
async def test_read_write_json_roundtrip(tmp_path):
    p = tmp_path / "a.json"
    await write_doc(p, {"k": 1})
    assert await read_doc(p) == {"k": 1}

@pytest.mark.asyncio
async def test_read_write_csv_roundtrip(tmp_path):
    p = tmp_path / "a.csv"
    await write_doc(p, [["h", "i"], ["1", "2"]])
    assert await read_doc(p) == [["h", "i"], ["1", "2"]]
```

- [ ] **Step 2: 运行确认失败**；**Step 3: 实现** 格式分发器（`_READERS/_WRITERS` dict）；**Step 4: 验证通过**（json/csv/yaml/xlsx 各一轮）；**Step 5: 提交** `feat(P0): 文件系统通用格式读写 fs.py`（若 `openpyxl` 未装先 `pip install` 并补 `scripts/libs` wheel）

---

### Task 5: @tool 扩展 risk 字段 + 基础工具集

**Files:**
- Modify: `core/tools/base.py`（`@tool` 增加 `risk` 参数，写进 schema）
- Modify: `core/tools/__init__.py`
- Create: `core/tools/basic.py`
- Create: `tests/test_tools_basic.py`

**Interfaces:**
- Consumes: `run_shell/run_python/read_doc/write_doc/env_probe`（Task 1-4）。
- Produces:
  - `@tool(description, risk="read"|"write"|"exec")`；`TOOLS.schemas()` 的每个 schema 增加 `"risk"` 字段。
  - 新工具（`core/tools/basic.py`）：`grep_file(pattern, path, ext=None)`、`find_files(name_pattern, dir=".")`、`read_file(path)`、`write_file(path, content)`(risk="write")、`parse_doc(path)`、`list_dir(path=".")`、`run_shell_tool(command)`(risk="exec")、`run_python_tool(code)`(risk="exec")、`system_probe()`。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_tools_basic.py
from core.tools import TOOLS
def test_risk_field_in_schema():
    names = {s["function"]["name"]: s for s in TOOLS.schemas()}
    assert names["write_file"]["risk"] == "write"
    assert names["system_probe"]["risk"] == "read"
```

- [ ] **Step 2: 运行确认失败**（risk 字段不存在）；**Step 3: 实现** base.py 加 `risk` 参数并把 `_build_schema` 结果附 `"risk"`；basic.py 用 @tool 注册 9 个工具（内部调 Task 1-4 的执行层）；**Step 4: 验证通过**；**Step 5: 提交** `feat(P0): @tool 增加 risk 分类 + 基础工具集 basic.py`

---

### Task 6: 编排层 session.py + intent.py

**Files:**
- Create: `core/orchestrator/__init__.py`
- Create: `core/orchestrator/session.py`
- Create: `core/orchestrator/intent.py`
- Create: `tests/test_orchestrator_intent.py`

**Interfaces:**
- Consumes: `core/llm/client.py` 的 `get_llm_client()`（复用现有 `stream_chat`）。
- Produces:
  - `enum SessionState: idle, understanding, chit_chat, forming_task, clarifying, confirming, executing, reporting, stopped, paused`
  - `class Session: state:SessionState; messages:list[dict]; task:Task|None; channel:OperatorChannel|None`
  - `class OperatorChannel(Protocol): async def ask(self, question:str)->str; async def notify(self, text:str)->None`（由 server/voice 实现）
  - `@dataclass IntentResult: type:str; summary:str`
  - `async def judge_intent(text:str, channel:OperatorChannel) -> IntentResult` — 用结构化 tool-calling 让 LLM 输出 `{"type":"chit_chat|task","summary":...}`；解析失败兜底 `{"type":"task"}`。

- [ ] **Step 1: 写失败测试**（session 状态迁移 + judge_intent 用 monkeypatch 假 LLM 返回结构化结果）
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现** session 状态机（`can_transition` 校验）；`judge_intent` 用 `stream_chat` 消费 `done.message.tool_calls` 解析意图。
- [ ] **Step 4: 验证通过**
- [ ] **Step 5: 提交** `feat(P0): 编排层会话状态机 + 意图判断`

---

### Task 7: task.py + clarify.py（任务形成与澄清）

**Files:**
- Create: `core/orchestrator/task.py`
- Create: `core/orchestrator/clarify.py`
- Create: `tests/test_orchestrator_task.py`

**Interfaces:**
- Consumes: `Session`、`OperatorChannel`、`judge_intent`。
- Produces:
  - `@dataclass Task: id:str; goal:str; params:dict; missing:list[str]; risk:str; state:str`
  - `async def form_task(session, intent) -> Task` — LLM 结构化提取 `{goal, params, missing[], risk}`。
  - `async def run_clarify(session) -> dict` — 对 `missing` 逐条 `channel.ask()`，收集答案回填 params；上限 `MAX_CLARIFY_ROUNDS=3`；返回最终 params。

- [ ] **Step 1: 写失败测试**（form_task 解析；run_clarify 用假 channel 连续回答后 params 补齐）
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**：form_task 复用 tool-calling 结构化输出；run_clarify 循环 `ask → 填 params → 重新检查 missing`。
- [ ] **Step 4: 验证通过**
- [ ] **Step 5: 提交** `feat(P0): 任务形成 + 澄清循环（问操作者）`

---

### Task 8: confirm.py（高影响确认）

**Files:**
- Create: `core/orchestrator/confirm.py`
- Create: `tests/test_orchestrator_confirm.py`

**Interfaces:**
- Consumes: `OperatorChannel`、`Task.risk`。
- Produces: `async def confirm_if_needed(task:Task, plan:str, channel:OperatorChannel) -> bool` — risk != "read" 时复述方案并 `ask("确认执行？")`，回答匹配 `{"确认","执行","可以","是"}` 返回 True；"信任"则写入 memory（P1 接入，此处返回 True 并 `notify` 记录）。risk=="read" 直接 True。

- [ ] **Step 1: 写失败测试**（read 自动 True；exec 需确认，答"确认"→True，答"取消"→False）
- [ ] **Step 2: 运行确认失败**；**Step 3: 实现**；**Step 4: 验证通过**；**Step 5: 提交** `feat(P0): 高影响操作确认层`

---

### Task 9: executor.py（执行循环）

**Files:**
- Create: `core/orchestrator/executor.py`
- Create: `tests/test_orchestrator_executor.py`

**Interfaces:**
- Consumes: `Task`、`TOOLS`、`CancellationToken`、`OperatorChannel`。
- Produces:
  - `async def execute_task(task:Task, channel:OperatorChannel, cancel:CancellationToken) -> dict` — ReAct 循环：`plan → act(调工具) → observe(回喂) → reflect(是否达成)`；收敛判定 + `MAX_STEPS=12`；每步检查 `cancel.is_cancelled`；返回 `{status:"done|failed|stopped", summary, steps:[...]}`。

- [ ] **Step 1: 写失败测试**（用假 LLM/假 TOOLS 脚本：能收敛到 done；步数超限→failed；cancel→stopped）
- [ ] **Step 2: 运行确认失败**；**Step 3: 实现**（参照现有 `core/agent.py` 的 ReAct，升级为可取消 + 收敛判定）；**Step 4: 验证通过**；**Step 5: 提交** `feat(P0): 执行循环 executor（plan/act/observe/reflect + 收敛 + 可取消）`

---

### Task 10: control.py（停止/中止控制器）

**Files:**
- Create: `core/orchestrator/control.py`
- Create: `tests/test_orchestrator_control.py`

**Interfaces:**
- Produces:
  - `class CancellationToken: def cancel(); @property is_cancelled:bool; def throw_if_cancelled()`（抛 `asyncio.CancelledError`）
  - `class StopController: token:CancellationToken; def stop_task(); def stop_step(); def pause(); def resume()`
- Consumes: `run_shell` 的 `cancel` 参数（Task 2）——在 shell 层与 executor 步进间传递同一 token。

- [ ] **Step 1: 写失败测试**（token cancel 后 executor 下一轮抛 CancelledError；pause/resume 状态切换）
- [ ] **Step 2: 运行确认失败**；**Step 3: 实现**；**Step 4: 验证通过**；**Step 5: 提交** `feat(P0): 停止/中止控制器（CancellationToken 贯穿）`

---

### Task 11: server.py 集成 + SSE 事件扩展

**Files:**
- Modify: `server.py`
- Modify: `web/src/api.ts`、`web/src/types.ts`
- Modify: `tests/test_server.py`

**Interfaces:**
- Produces:
  - `POST /api/voice/utter` body `{"text":...}` → 走 orchestrator（闲聊直接回复 SSE；任务进入澄清/确认/执行）。
  - `POST /api/task/{id}/stop` → `StopController.stop_task()`。
  - `GET /api/env` → 返回 `environment.md` 文本。
  - SSE 新增事件：`task_state`、`question`、`confirm`、`stop_ack`（向后兼容，旧事件不变）。
- Consumes: `run_orchestrator`（把 Session+intent+task+clarify+confirm+executor 串成一条 `async` 管线，产出事件流）。

- [ ] **Step 1: 写失败测试**（TestClient：`/api/voice/utter` 在 monkeypatch 的 orchestrator 下产出 `question` 事件；`/api/task/x/stop` 返回 ack；`/api/env` 返回 md）
- [ ] **Step 2: 运行确认失败**；**Step 3: 实现**（新端点 + `_sse` 透传新事件）；**Step 4: 验证通过**；**Step 5: 提交** `feat(P0): server 集成编排管线 + SSE 新事件`

---

### Task 12: 桌面语音监听 wake.py + 命令词

**Files:**
- Create: `core/voice/wake.py`
- Create: `tests/test_voice_wake.py`（命令词解析逻辑可单测）

**Interfaces:**
- Produces:
  - `class WakeListener: async def start(on_utterance: Callable[[str], Awaitable]); def stop()` — 本地 Vosk 常驻麦克风，识别到唤醒词后录音→ASR→`on_utterance(text)`。
  - `def is_stop_command(text:str) -> bool` — 命中 `{"停止","取消","暂停","够了"}` 返回 True（即时转 `StopController`，不走 LLM）。

- [ ] **Step 1: 写失败测试**（`is_stop_command` 命中/不命中；唤醒词配置读取）
- [ ] **Step 2: 运行确认失败**；**Step 3: 实现**（`scripts/libs` 需补 `vosk` wheel；唤醒词模型复用 `web/public/models/vosk-model-small-cn-0.22.tar.gz` 或独立下载）；**Step 4: 验证通过**（麦克风部分留手动冒烟）；**Step 5: 提交** `feat(P0): 桌面语音监听 + 停止命令词`

---

### Task 13: 前端面板扩展（任务流/待确认/停止）

**Files:**
- Modify: `web/src/views/ConsolePage.vue`（新增 Tab：任务）
- Create: `web/src/components/console/ConsoleTaskView.vue`、`ConsoleEnvView.vue`、`ConfirmCard.vue`
- Modify: `web/src/api.ts`（`utter/stopTask/getEnv` + SSE 新事件 handler）

**Interfaces:**
- Consumes: 现有 `useAssistant` 单例、`streamChat`（扩展事件）、新 `/api/*`。
- Produces: 任务视图（任务列表 + 每步执行流）、待确认卡片（confirm 事件 → 确认/取消按钮）、停止按钮、环境视图（读 `/api/env` 渲染 md）。

- [ ] **Step 1: 先改 api.ts/types.ts（类型 + 端点）**
- [ ] **Step 2: 写组件骨架并接 SSE 事件**（`onTaskState/onQuestion/onConfirm/onStopAck`）
- [ ] **Step 3: `cd web && npm run build`** 类型检查通过
- [ ] **Step 4: 手动冒烟**（`py -3.14 main.py serve`：语音/输入"把桌面 readme.txt 复制到下载"→ 澄清提问 → 确认 → 执行 → 停止按钮可中断）
- [ ] **Step 5: 提交** `feat(P0): 前端任务/环境视图 + 停止与确认交互`

---

## P0 验收清单

- [ ] 语音（或面板输入）"把桌面 xx.txt 复制到下载"：意图判断→任务形成→澄清提问→（操作者回答）→确认→执行→汇报，全链路跑通。
- [ ] 执行中语音/按钮"停止"立即中止整个任务并 kill 子进程。
- [ ] 环境感知：首次运行生成 `environment.md`；`/api/env` 可读；"更新环境信息"可增量刷新。
- [ ] 基础工具（grep/find/读写/parse/run_shell/run_python/system_probe）均注册且 `risk` 分类正确。
- [ ] 全部 pytest 通过；`npm run build` 通过。

## P0 审查清单（每个 Task 完成后对照）

- [ ] 接口签名与任务间引用一致（`CancellationToken`/`OperatorChannel`/`Task` 贯穿正确）。
- [ ] 无沙箱但高风险操作全部过 `confirm.py`；只读自动执行。
- [ ] 所有子进程路径都能被 kill（`kill_tree` 覆盖）。
- [ ] SSE 新事件向后兼容（旧事件未破坏）。
- [ ] 每个 Task 有独立测试且全绿；有独立 commit。
