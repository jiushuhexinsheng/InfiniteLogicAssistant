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
python -m pytest tests/ -q      # 后端单元测试（编排 / 工具 / 记忆 / RAG / MCP / Skills / 定时 / API）
python -m mypy core/ server.py  # 后端静态类型检查
cd web && npm test              # 前端单元测试（Vitest：store / SSE 解析）
cd web && npm run build         # 前端类型检查（vue-tsc）+ 生产构建
```

## 后端结构要点

- **配置**：`core/config/` 包统一加载（pydantic 强类型）。pydantic 模型在 `schema.py`，YAML 读取与密钥注入在 `loader.py`，全局单例 / 热重载 / profile 解析在 `runtime.py`，`__init__.py` 兼容 re-export。新增配置段：`schema.py` 加 pydantic 模型 → `config.yaml.example` 补示例 → `editable_snapshot()` 补设置页快照。
- **API**：新端点加进 `core/api/` 对应路由模块（`APIRouter`），`server.py` 已挂载 `/api` 前缀。
- **工具**：`core/tools/` 用 `@tool(desc, risk)` 注册，`__init__.py` import 即注册。
- **编排**：`core/orchestrator/` 各模块单一职责；`events` 队列走 SSE，`session.notify/ask` 走人类在环通道。
- **会话**：`core/api/state.py` 管理注册表（自动清理 + 落盘），新端点用 `state.get_session/get_controller`。
- **安全**：非 localhost 绑定时新端点自动被 `X-API-Token` 中间件保护；工具执行自动写审计日志。

## 前端结构要点

- 状态：`web/src/composables/assistant/store.ts` 模块级单例（消息/localStorage 持久化/唤醒模型进度）。
- 对话流：`useChat.ts` → `streamUtter`（唯一 agent 路径，含澄清问答卡片）。
- SSE 解析：`web/src/api.ts::streamUtter`（支持 AbortSignal 取消与网络重试）。
- 新组件：`web/src/components/assistant/`（悬浮球）、`console/`（控制台 Tab），跨页复用放 `ui/` 原语组件（UiButton/UiInput/UiSelect/UiToggle/UiCard/UiModal 等 + 语义令牌）。
- GUI 自动化（`pyautogui`/`pygetwindow` 等）已打成 wheel 入 `scripts/libs/`，离线 `--no-index` 完整可用。

## 编码约定

- 后端中文 docstring；前端 `<script setup lang="ts">`。
- 新增依赖离线 wheel 需补 `scripts/libs/`。
- 每个功能先写失败测试（TDD），再实现，再验证，再提交。
