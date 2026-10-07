# 03 · 追问/续聊窗口正式化 + 浏览器端 sherpa-onnx KWS 落地

> 借鉴：Home Assistant（conversation 注册表、start/continue conversation 追问窗口）、
> Porcupine WASM（浏览器端实时 KWS 可行性佐证）、本项目后端 `kws.py` 已有本地闸门。
> 优先级 P1。阶段一独立可用；阶段三（浏览器 KWS）与 02 批次三无依赖。

## 实施状态

- **⚠️ 2026-10-07 取消限时回答（本文件 A 节的「现状 #2」已作废）**：待答 8s 无应答 → `standby`、
  喤醒回原问题的机制已整体删除——回答**永不限时**；待答期间改为**先判唤醒词**（命中即 `stop`
  弃题开新轮，未命中照旧当答案）。`vad.answer_timeout_ms` 保留键名、语义收敛为**裸唤醒后的
  等指令窗**（本文正文中的「待答 8s」字样是历史记录，实现以上述契约为准）。
- **A 节（续聊窗口）已完成（2026-09-29）**：`AsstState` 新增 `followup`；wakeFsm 新增
  `followup_open` / `followup_expire` 事件；配置 `voice.vad.followup_window_ms`（默认 6000，
  0=关闭回旧「3s 回聆听」行为；同样因 editable_snapshot 只暴露 vad/wake_word 而放 vad 段）；
  唤醒编排：done/error 开窗（唤醒开启且窗口>0）、播报结束重武装满窗、`processSegment` 与
  `handleLocalResult`（webspeech）各插免唤醒分流（先过唤醒词判定保持兼容）、toggleWake 的
  「回合刚结束」窗口集合纳入 followup；设置页/配置模板/README 同步，gen:api 已重跑。
- **B 节（浏览器 KWS）Go/No-Go = No-Go（2026-09-29 评估）**：
  - npm `sherpa-onnx@1.13.8` 仅含 `sherpa-onnx-wasm-nodejs.wasm`（README：Node ≥ 18），无浏览器构建；
  - GitHub release wasm 资产只有 TTS/VAD/语音增强，无 KWS 浏览器包；
  - 自建路径（emscripten 编 sherpa fork / onnxruntime-web 手搬 zipformer KWS 状态机）维护成本
    高，增量收益仅「提示音提前 ~1.5s + 省一次 localhost 快检往返」——判定本地化零云成本已由
    后端 KWS 闸门保证。
  - 处置：`sherpaKwsProvider` 占位曾保留待官方浏览器构建；**2026-10-07 按 P3-8 改为删除**
    ——占位 `isAvailable()` 恒 false 是死代码（auto 链永不 push），评估证据仍存于本文件
    §B（将来若官方发布浏览器构建，按 §B 设计重新引入）。
- 测试：vitest 245 绿（新增 wakeFsm 3 / 续聊窗口 4）、pytest 494 绿、mypy 干净、build 通过。

## A. 续聊窗口（followup window）

### 1. 现状

| # | 现状 | 位置 | 差距 |
|---|---|---|---|
| 1 | 只有**提问**场景免唤醒：`question_ready → awaiting_answer`，答后 `clearAnswerTimer` | `wakeFsm.ts:44-52`、`wakeOrchestrator.ts:295,472` | ✅ 已有雏形 |
| 2 | 待答 8s 无应答 → `standby`，喊唤醒词回到原问题 | `wakeFsm.ts:54-62`、`wakeOrchestrator.ts:113-121` | ✅ 已有 |
| 3 | 回合结束（done/error）后 3s 回 `listening`，**之后必须喊唤醒词**才能再说下一句 | `wakeOrchestrator.ts:87,716-724` | ❌ 无「助手说完→用户自然接话」窗口 |
| 4 | 会话 = 内存注册表 + 30min TTL，无对外查询 | `core/api/state.py:18-37` | 刷新后 awaiting/followup 语义丢失（依赖 01 批 2 恢复） |

### 2. 目标

助手播报结束后的 `voice.followup_window_ms`（默认 6000，0=禁用）内，用户语音段**免唤醒直接作为新指令**；窗口内每来一段有效语音即刷新窗口；窗口关闭回常规唤醒监听。与「待答窗口」「回声护栏」三层时间语义并存、互不抢占。

### 3. 设计

**状态机**（`web/src/composables/assistant/wakeFsm.ts` + `store.ts` AsstState）：

```
新增状态 followup（AsstState 增一员）
迁移：
  done | error  + speaking 变 false（无 pendingQuestion） → followup，装 followupTimer（followup_window_ms）
  followup + 段到达（过回声护栏、非空） → 消费为指令 → thinking（sendText 后随现有流状态）
  followup + Timer 到期 → listening
  followup + wake_detected（用户仍喊唤醒词） → 走现有唤醒流程（不冲突，等价于跳过窗口）
  followup + question_ready（新问题插播） → awaiting_answer（问句优先，窗口挂起）
```

- 改造点：现有 `DONE_RESET_MS=3000` 的「done 后 3s 回 listening」watch（`wakeOrchestrator.ts:716-724`）→ 改为「done 后进 followup 窗口（可配 ≥3s），窗口结束才回 listening」。
- **`processSegment` 分流顺序插入**（`wakeOrchestrator.ts:268-383`，现顺序：回声护栏 → pendingQuestion → awaitingCommand → 熔断门 → …）：

```
回声护栏 → pendingQuestion(作答) → awaitingCommand(指令)
        → followup 窗口内: 转写(免 KWS/免唤醒判定) → sendText → 刷新窗口
        → 熔断门 → 上传节流 → 唤醒判定(KWS/cloud) …
```

- **成本口径**：followup 段要抬文本必然调云端 ASR（`/voice/transcribe`；webspeech 模式本地）——与 `cloud` 模式同成本。缓解：窗口默认 6s 且仅在助手刚说完时开启，回声护栏 1.2s 仍前置挡尾音；`followup_window_ms=0` 可整体关闭。audit 记 `via=followup`（上传记账口径新增枚举，README 隐私节同步一句）。
- **配置**：`voice` 段新增 `followup_window_ms: int = 6000`（`core/config/schema.py` / `api/schemas.py` / `configDefs.ts` 三处同步；设置页 VoiceCard 加输入项，tooltip 写清三层窗口：回声 1.2s / 待答 8s / 续聊 6s）。
- **与 01 的衔接**：followup 是纯前端窗口，不做服务端注册表——HA 式 `conversation_id` 的等价物就是 `session_id` + `qid` 配对（已具备），完整 all_sessions 注册表**不引入**（`state.sessions` 已是其轻量版）。

### 4. 测试

- vitest（`wakeFsm.spec` + `useWakeWord.spec` 扩展）：done→followup 迁移；窗口内段免唤醒转 sendText；窗口刷新；到期回 listening；窗口内喊唤醒词兼容；窗口内新问题插播进 awaiting_answer；`followup_window_ms=0` 行为与现状全同；followup 段 audit 口径（经 api mock 断言 `transcribe` 被调）。

---

## B. 浏览器端 sherpa-onnx KWS（原 `sherpaKwsProvider` 占位）

> **状态（2026-10-07）**：占位文件 `web/src/composables/assistant/wake/sherpaKwsProvider.ts`
> 已随 P3-8 删除（No-Go 评估见下，死代码不留）；本节保留为将来启用的设计底稿。
> 下文对占位文件与 `wakeChain` 的行号引用是**删除前的历史快照**。

### 1. 现状（占位删除前）

- `sherpaKwsProvider.ts`：纯占位——`isAvailable()` 恒 false（`wasmReady` 从未置真）、`detect()` 恒 miss、`init()` 打日志 TODO（`sherpaKwsProvider.ts:49-84`，接入步骤注释在 26-38 行）。
- `wakeChain.getChain('auto')` 里 sherpa 排第一，但因 `isAvailable()===false` 实际不参与（`wakeChain.ts:67-98`）。
- 后端已有同款闸门：`core/voice/kws.py`（sherpa-onnx zipformer-wenetspeech 3.3M，模型在 `models/`，**随仓库入库**），`POST /api/voice/wake/check` 毫秒级本地快检、零云端调用。
- 段录音器输出 `audio/webm` blob（`useSegmentRecorder.ts:101-131`），KWS 需要 16kHz PCM 帧——**接口错配是占位未落地的根因之一**。

### 2. 增量价值（诚实口径）

| 收益 | 说明 |
|---|---|
| **段内提前命中** | 现链路必须等 VAD 静音 1.5s 切段后才快检；流式 KWS 在用户说到唤醒词的**当下**即命中 → 提示音提前，打掉「1.5s 物理下限」（README 已把它列为下限） |
| 免后端往返 | 命中判定不再依赖 `POST /voice/wake/check`，后端未起/断网也能本地判 |
| 与云成本无关 | 判定纯本地，`auto` 链命中后跳过云端 wakeCheck 请求 |

不承诺：完全离线对话（指令抬取仍需云端 ASR，除非 webspeech）。

### 3. 设计

**资产**：
- 依赖：`sherpa-onnx` 官方 npm 的 WASM 运行时（若包不满足 kws streaming API，备选 onnxruntime-web 手跑 encoder/joiner —— 列为风险项，阶段一先评估，见 §4）。
- 模型文件复用 `models/sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01/`（encoder/decoder/joiner int8 + tokens + `keywords.generated.txt`）。**不复制进 web/**：`server.py` 新增静态路由 `GET /models/kws/{path}`（仅当 `voice.kws.local.enabled` 时挂载，目录白名单 = 该模型目录，防路径穿越）。

**架构**：

```
AudioWorklet(采 16kHz Float32 帧, 30ms)
   └→ Web Worker（kws.worker.ts）
         sherpa-onnx WASM spotter 实例（模型从 /models/kws 拉取）
         命中 → postMessage({hit, ts})
主线程 sherpaKwsProvider：
   init()   → 拉模型 + 起 worker → wasmReady=true（isAvailable 才为 true）
   feed(pcm)→ 由 orchestrator 在 segmenter 活跃期持续喂帧
   detect(blob) → 返回「该段时间窗内的命中缓存」{matched, command:''}
                  （KWS 不产文本；尾随指令仍走 extractTrailingCommand / transcribe，与后端 local 模式语义一致）
```

- **PCM 来源两阶段**：
  - 阶段一（打通）：`decodeAudioData` 对整段 webm 解码 → 喂 worker（段级，命中窗口=整段）。接口与现有 `detect(blob)` 天然对齐。
  - 阶段二（流式）：`AudioWorklet` 从采集流实时喂帧，**段未结束即可命中** → 提前 `playBeep` + 开指令窗。此时 `detect(blob)` 退化为「查缓存是否已在本段窗内命中」。
- **链路接入**（`wakeOrchestrator.ts` 现快检位置 351-379）：

```
非 cloud 模式:
  sherpa.isAvailable() 且本段有帧级命中缓存 → 直接 beep + 指令窗 + extractTrailingCommand（跳过 api.wakeCheck）
  sherpa.isAvailable() 但无命中 → 仍走 api.wakeCheck（后端 KWS 是第二道，语义不变）
  sherpa 不可用 → 现状完全不变（KWS bypass → fullDetect 回退链保持）
```

- **熔断整合**：sherpa 本地命中/未命中**不计入**云端失败熔断计数（本地判定无网络语义）；`detectInChain` 中 sherpa 仍排 `auto` 链首位，但 `detect` 抛错（worker 崩）→ 置 `wasmReady=false` 并降级现状，**不触发熔断**（全失败才熔断的现有语义保留在云端 provider 上）。
- **配置**：`voice.kws.local = {enabled: bool = false, model_base_url: str = '/models/kws', sensitivity: float}`（与后端 `voice.kws` 阈值同名同义）。默认 **false**（阶段一灰度），设置页 VoiceCard 增开关 + 「本地 KWS（浏览器）」徽章。
- **共享测试向量**：命中语义复用 `tests/data/wake_vectors.json` —— worker 侧用同一批向量的**音频特征替身**（mock spotter 输出序列）验证「命中窗口/缓存查询」逻辑与后端口径一致。

### 4. 实施步骤

| 批次 | 内容 | 验收 |
|---|---|---|
| **批 1** | 阶段一评估：npm WASM 包能力验证（kws streaming API、模型格式兼容）——**Go/No-Go 决策点** | 演示 worker 内跑通一次 detect |
| **批 2** | `/models/kws` 静态路由 + worker + 段级 `detect` + `isAvailable` 状态机 + 配置三处同步 | 开关开启、`auto` 链参与；关闭=现状 |
| **批 3** | AudioWorklet 流式喂帧 + 段内提前命中 + 快检短路 | 提示音早于 VAD 切段（可观测时间戳） |
| **批 4** | verify-voice 台接入 + 共享向量用例 | 双端语义用例绿 |

**风险与回退**：批 1 No-Go（包能力不足/onnxruntime-web 不兼容）→ 保留占位，转投「后端快检已满足判定本地化」结论，把资源转给 A（续聊窗口）；模型体积 ~10MB 首拉取在设置页显示进度。

## 测试计划（汇总）

- pytest：`voice.kws.local` schema 段校验；`/models/kws` 路由（启用/禁用/路径穿越 404）。
- vitest：provider 状态机（init 成功/失败/二次 init 幂等）、缓存命中窗口语义（共享向量驱动）、`auto` 链参与与降级、worker 崩溃不触发熔断。
- 手动：verify-voice 台「段内提前唤醒」延迟对比（改造前后提示音时间戳）。
