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

## 语音隐私边界

⚠️ **2026-09-13 唤醒链路重构后，语音不再有本地判定环节**：唤醒词由**云端 ASR** 判定。

- **每次本地 VAD 判到人声，都会把该音频片段上传到云端 ASR（默认 `api.xiaomimimo.com`），
  无论是否说出唤醒词。** 没说唤醒词的那段话同样出本机。
- VAD 是**本地闸门**，只做「滤静音 + 滤过短片段」以**减少**上传次数，**不是隐私屏障** ——
  它降低的是调用量与成本，不是数据出本机的范围。
- 等待操作者作答期间更是如此：每一段都当作答上传（`/api/voice/transcribe` → `/api/voice/answer`）。
- 唤醒判定走 `POST /api/voice/wake`，后端每收一段记一行审计（`data/audit.log`，含转写文本前
  80 字）—— 这是统计调用量与成本的唯一依据。
- **助手播报期间麦克风被释放**（`stopListening` 停掉音频轨道），既避免自触发，也意味着播报时
  间段不取音；但这不是「隐私开关」，只是链路行为。
- **关闭方式**：再次点悬浮球上的 mic 徽章（或设 `voice.wake_word.enabled: false`），
  取麦与上传即停止；不接受「人声片段送到第三方 ASR」时请改用文字输入。

## 审计日志

- 工具执行（工具名、参数、风险级、结果状态）与高风险确认决策（同意/拒绝/原因）写入 `data/audit.log`。
- **唤醒上传**同样逐条记入 `data/audit.log`（`wake matched=… chars=… command=… text=…`），
  是统计云端 ASR 调用量与成本的唯一依据（见「语音隐私边界」）。
- 与 `data/agent.log` 分离，独立文件保留 90 天。
- 实现点：`core/tools/base.py`（TOOLS.acall/call）、`core/orchestrator/confirm.py`。

## 全链路可中止

`CancellationToken` 从会话 → 任务 → 工具 → 子进程贯穿；
`run_shell` 支持 `taskkill /T` 进程树强杀；`POST /api/task/{sid}/stop` 随时中止。

## 数据卫生

- `config.yaml`（含 API Key）与 `environment.md`（含本机信息）不入仓库。
- 会话完成落盘 `data/tasks/<id>.json`，可审计/回放。
