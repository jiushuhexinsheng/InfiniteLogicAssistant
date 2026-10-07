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

**本地 KWS 唤醒判定（2026-09-26 起，`voice.kws.enabled` 默认开启）**：唤醒判定在**本机**
完成（sherpa-onnx 关键词检测），这是当前的隐私主边界。

- **没说唤醒词的音频（电视声/闲聊）在本机直接丢弃 —— 不出本机、不上云、不花钱。**
  只有 KWS 听到唤醒词的那段，才上传到你 `config.yaml` 里 `asr` 指向的云端 ASR
  抬取**指令文本**（转写是「把语音变文字」，不是唤醒判定本身）。
- `cloud` 模式（设置页「语音」可切）**旁路本地闸门**：每次人声段都上云判定，最大召回，
  但隐私面回到「每段人声都出本机」。`webspeech` 模式走浏览器识别（Chrome 中文实际经
  Google 服务器，并不更私密）。
- **KWS 模型缺失时闸门自动旁路**（回退云端判定）并在启动日志注明 —— 此时隐私面同 cloud 模式。
- VAD 是**本地闸门**（滤静音、滤过短片段），KWS 是**本地判定闸门**（滤非唤醒语音）；
  等待作答期间的音频仍会当作答上传（`POST /api/voice/transcribe`，再由 `/api/voice/answer`
  把**文本**投给编排层）。
- **上传即记账**（`data/audit.log`）：`audio-upload via=wake|transcribe` 是**真正上云**的音频
  （含转写文本前 80 字）；`kws-gate hit/skip=` 是**本地判定**记账（非上传，不进成本口径）。
  `grep -c 'audio-upload via=' data/audit.log` 即云端上传总次数 —— 统计调用量与成本的依据。
  （`/api/voice/answer` 只回传文本、不出音频，不记上传审计。）
- **助手播报期间麦克风被释放**；播报结束后 1.2 秒内音频整体丢弃（回声护栏——助手自称
  「衍衡」，防止它自己的声音被误唤醒或代答）。
- **关闭方式**：再次点悬浮球上的 mic 徽章（或设 `voice.wake_word.enabled: false`），
  取麦即停止；不接受「唤醒片段送到第三方 ASR」时请改用文字输入，或等本地 ASR 落地。

## 审计日志

- 工具执行（工具名、参数、风险级、结果状态）与高风险确认决策（同意/拒绝/原因）写入 `data/audit.log`。
- **云端 ASR 上传**逐条记入 `data/audit.log`，两条通道共用前缀 `audio-upload via=`：
  `via=wake matched=… chars=… command=… text=…`（唤醒命中后为提取指令的转写）、
  `via=transcribe chars=… text=…`（作答 / 指令）。
  `grep -c 'audio-upload via=' data/audit.log` 即云端上传总次数（成本口径）。
- **本地 KWS 判定**另记 `kws-gate hit=1` / `kws-gate skip=1`（前缀不同：它不是上传，
  **不得混入 `audio-upload` 成本口径**；skip = 被闸门挡掉的背景声/闲聊）。
- **通话模式**（`/api/voice/call/*`）：会话开/关记 `call-start` / `call-stop`；漏斗各级丢弃与
  异常记 `call-funnel`（本地判定，非上传）；**L2 云端转写是真上传**，记
  `audio-upload via=call-segment`（计入成本口径，与 wake/transcribe 同前缀）。
- 与 `data/agent.log` 分离，独立文件保留 90 天。
- 实现点：`core/tools/base.py`（TOOLS.acall/call）、`core/orchestrator/confirm.py`。

## 全链路可中止

`CancellationToken` 从会话 → 任务 → 工具 → 子进程贯穿；
`run_shell` 支持 `taskkill /T` 进程树强杀；`POST /api/task/{sid}/stop` 随时中止。

## 数据卫生

- 密钥零落库：`config.yaml` 不含密钥（模板 `config.yaml.example` 入库）；
  `config.secrets.yaml`（密钥）与 `environment.md`（含本机信息）不入仓库。
- 会话完成落盘 `data/tasks/<id>.json`，可审计/回放。
