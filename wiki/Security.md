# 安全模型

设计基线：**无沙箱**，以「人类在环确认 + 审计」兜底。

## 访问控制

- **默认只绑定 `127.0.0.1`**。
- `server.host` 改为非 localhost 时，**必须**设置 `server.api_token`，否则拒绝启动。
- 设置后所有 `/api/*` 请求需携带 `X-API-Token` 请求头（`core/api` 路由之上有中间件统一校验）。
- CORS：`server.cors_origins` 默认空 = 禁止跨域。

## 操作确认策略

| 操作类别 | 策略 |
|----------|------|
| 只读（查文件/搜索/查状态） | 自动执行 |
| 写/覆盖/删除/移动 | 默认先 `confirm`（`core/orchestrator/confirm.py`） |
| 执行任意 shell/py/安装软件 | 默认 `confirm` |
| 无人值守（定时任务） | 澄清停止、确认拒绝，只读自动执行 |

## 审计日志

- 工具执行（工具名、参数、风险级、结果状态）与高风险确认决策（同意/拒绝/原因）写入 `data/audit.log`。
- 与 `data/agent.log` 分离，独立文件保留 90 天。
- 实现点：`core/tools/base.py`（TOOLS.acall/call）、`core/orchestrator/confirm.py`。

## 全链路可中止

`CancellationToken` 从会话 → 任务 → 工具 → 子进程贯穿；
`run_shell` 支持 `taskkill /T` 进程树强杀；`POST /api/task/{sid}/stop` 随时中止。

## 数据卫生

- `config.yaml`（含 API Key）与 `environment.md`（含本机信息）不入仓库。
- 会话完成落盘 `data/tasks/<id>.json`，可审计/回放。
