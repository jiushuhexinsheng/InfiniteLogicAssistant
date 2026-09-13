# 安全模型

设计基线：**无沙箱**，以「人类在环确认 + 审计」兜底。

> ⚠️ **2026-09-13 起确认默认关闭**：`permissions` 三档默认全放行（按用户要求），因此下表中
> 写入与执行类操作**默认都不再询问**。收紧方式见「收紧方式」一节，或控制台「设置 → 权限」。

## 访问控制

- **默认只绑定 `127.0.0.1`**。
- `server.host` 改为非 localhost 时，**必须**设置 `server.api_token`，否则拒绝启动。
- 设置后所有 `/api/*` 请求需携带 `X-API-Token` 请求头（`core/api` 路由之上有中间件统一校验）。
- CORS：`server.cors_origins` 默认空 = 禁止跨域。

## 操作确认策略

| 操作类别 | 策略 |
|----------|------|
| 只读（查文件/搜索/查状态） | 自动执行 |
| 写/覆盖/删除/移动 | 由 `permissions` 策略决定；**默认放行**（改 `tiers.write` 为 `ask` 即恢复询问） |
| 执行任意 shell/py/安装软件 | 同上，**默认放行**（改 `tiers.exec` 为 `ask` 即恢复询问） |
| 任务开始时的计划级确认 | 与逐工具确认**共用同一份 `permissions`**；放行时仍播报计划，只是不阻塞 |
| 无人值守（定时任务） | 澄清停止、确认拒绝，只读自动执行（**不受默认放行影响**：无确认通道时高风险一律拒绝） |

### 收紧方式

改 `config.yaml` 的 `permissions`，或用控制台「设置 → 权限」：

```yaml
permissions:
  tiers: { read: allow, write: ask, exec: ask }   # 恢复「写/执行需确认」
  rules:
    - { match: "run_*", action: deny }            # 按工具名 glob；deny 单调短路，不可被翻案
```

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
