# 开发指南

## 环境

- Python 3.14+（Windows x64；离线 wheel 在 `scripts/libs/`）
- Node 20+（前端 Vue3 + Vite + TS）

```bash
pip install -r requirements-dev.txt   # pytest + pytest-asyncio + mypy
cd web && npm install
```

## 测试

```bash
pip install -r requirements-dev.txt   # pytest + pytest-asyncio + mypy
python -m pytest tests/ -q      # 后端单元测试（收集前先做 requirements 漂移预检：缺包/版本不一致直接拦截）
python -m mypy core/ server.py  # 后端静态类型检查
cd web && npm test              # 前端单元测试（Vitest：store / SSE 解析 / 唤醒链）
cd web && npm run build         # 前端类型检查（vue-tsc）+ 生产构建
cd web && npm run gen:api       # 后端 response_model 改动后重新生成前端类型
```

> 唤醒判定的前后端语义由共享测试向量 `tests/data/wake_vectors.json` 在 pytest 与 vitest
> 双端共同钉住——改任一侧匹配规则，两侧测试必须同时变绿。

## CI（`.github/workflows/ci.yml`）

- **后端**（windows-latest / Python 3.14）：mypy + pytest + **gen:api 同步校验**
  （重新生成 `generated.ts` 后 `git diff --exit-code`，与后端 schema 不同步即失败）。
- **前端**（ubuntu-latest / Node 22）：`npm run build`（vue-tsc 类型检查）+ `npm test`。

## 后端结构要点

- **配置**：`core/config/` 包统一加载（pydantic 强类型）。pydantic 模型在 `schema.py`，YAML 读取与密钥注入在 `loader.py`，全局单例 / 热重载 / profile 解析在 `runtime.py`，`__init__.py` 兼容 re-export。新增配置段：`schema.py` 加 pydantic 模型 → `config.yaml.example` 补示例 → `editable_snapshot()` 补设置页快照。
- **容器**：全局服务生命周期集中在 `core/container.py` 的 `AppContext`（server lifespan 调 `start()/shutdown()`）；各模块 `get_xxx()` 委托容器，测试 monkeypatch `get_xxx` 的既有 mock 方式不变。
- **API**：新端点加进 `core/api/` 对应路由模块（`APIRouter`），`server.py` 已挂载 `/api` 前缀；响应模型写进 `core/api/schemas/` 分域模块（`response_model=`）→ 改完跑 `npm run gen:api` 同步前端类型（CI 会校验同步）。
- **工具**：`core/tools/` 用 `@tool(desc, risk)` 注册，`__init__.py` import 即注册；确认与否由 `core/tools/policy.py` 按 `permissions` 策略求值。
- **编排**：`core/orchestrator/` 各模块单一职责；`events` 队列走 SSE，`session.notify/ask` 走人类在环通道；系统提示词统一取自 `core/prompts.py`。
- **会话**：`core/api/state.py` 管理注册表（自动清理 + 落盘），新端点用 `state.get_session/get_controller`；对话线持久化在 `core/session/history.py`（`data/history.db`），成功任务存档与相似检索在 `core/tasks/store.py`。
- **安全**：非 localhost 绑定时新端点自动被 `X-API-Token` 中间件保护；工具执行自动写审计日志。

## 前端结构要点

- 状态：`web/src/composables/assistant/store.ts` 模块级单例（消息/localStorage 持久化）；`ChatMessage.blocks` 为事实源、`text` 为派生投影。
- 消息块协议：`web/src/blocks/`（types / registry 注册协议 / normalize 事件→块流 / speech TTS 管线）；块组件在 `components/blocks/`，新块类型 `registerBlock` 一行注册即插即用。
- 对话流：`useChat.ts` → `streamUtter`（唯一 agent 路径）；SSE 解析在 `api.ts::streamUtter`（AbortSignal 取消 + 网络重试）。
- 唤醒：`composables/assistant/wake/`（wakeOrchestrator 编排 / wakeChain 回退链 / 各 provider）；`wakeMatch.ts` 前端拼音匹配（Web Speech 路径）。
- 新组件：`web/src/components/assistant/`（悬浮球）、`console/`（控制台 Tab），跨页复用放 `ui/` 原语组件（UiButton/UiInput/UiSelect/UiToggle/UiCard/UiModal 等 + 语义令牌）。
- GUI 自动化（`pyautogui`/`pygetwindow` 等）已打成 wheel 入 `scripts/libs/`，离线 `--no-index` 完整可用。

## 编码约定

- 后端中文 docstring；前端 `<script setup lang="ts">`。
- 新增依赖离线 wheel 需补 `scripts/libs/`。
- 每个功能先写失败测试（TDD），再实现，再验证，再提交。
