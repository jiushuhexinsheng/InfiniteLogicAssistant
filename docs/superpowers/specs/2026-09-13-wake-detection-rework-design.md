# 唤醒链路重构（子项目 1：VAD → KWS(API) → ASR）

> 本 spec **只覆盖 4 个子项目中的第 1 个**。其余三个的边界见文末「后续子项目」，各自走独立的 spec → 计划 → 实施。

## 背景：为什么必须改

2026-09-13 把唤醒词从「小逻小逻」改为「衍衡」「洛吉斯」后，**唤醒完全失效**。

实测（假麦克风把音频喂给真实引擎，打印 Vosk 实际转写）：

| 说的 | Vosk 小模型听成 | 命中 |
|---|---|---|
| 衍衡 | 眼含 / 也行 | ❌ |
| 洛吉斯 | 若 / 弱激素 / 若缉私 | ❌ |
| 衍衡衍衡 | 演行 / 演着演着 | ❌ |
| 洛吉斯助手 | 若集资助手 | ❌ |
| 小逻小逻（对照） | 小罗 小罗 / 小逻辑 | ✅ 2/3 |

**对照组是关键**：同一套代码、同一条链路，旧词命中、新词全灭 —— 问题在**模型能力**，不在词。

同一段音频喂给云端 ASR（`mimo-v2.5-asr`，项目已配置）：

| 说的 | 云端 ASR | 结论 |
|---|---|---|
| 洛吉斯 | `洛吉斯。` | **一字不差** |
| 衍衡 | `燕恒。` | 差一个同音字 |
| 小逻小逻 | `小罗小罗。` | 正确 |

**所以词没问题，是 Vosk 小模型不行。** 而换大模型（`vosk-model-cn-0.22`，1.36GB）不可行：浏览器 WASM 放不下，且实测下载仅 ~15 KB/s（需 24 小时），HuggingFace 不可达。

「小逻小逻」按用户要求**废弃**，故 Vosk 一个能用的唤醒词都不剩 —— 一并移除。

## 目标

1. 唤醒重新可用：「衍衡」或「洛吉斯」
2. 支持一句话说完：「衍衡，帮我查天气」
3. 不再依赖 Vosk

## 非目标（留给后续子项目）

- 本地 KWS（sherpa-onnx，拼音自定义词）→ 子项目 2
- 本地 ASR → 子项目 3
- 有序回退链 + 能力探测（学 openclaw）→ 子项目 4

---

## 架构

```
麦克风 ── 单次 getUserMedia（不再由 Vosk 引擎独占）
  │
  ├─ 常驻本地 VAD（AnalyserNode，纯本地、不上传）
  │     └─ 第一道闸：只有疑似人声的片段才出本机
  │        │ 人声起止
  │        ▼
  │     分段录音（MediaRecorder → blobToWavBase64，复用现有 api.transcribe 的转换）
  │        │
  │        ▼
  │   POST /api/voice/wake  { audio_base64 }
  │        │  后端：ASR 转写 → 唤醒词匹配 → { matched, command, text }
  │        │
  │        ├─ matched 且 command 非空 → 直接当指令 → /api/voice/utter
  │        ├─ matched 且 command 为空 → 提示音 → 开录指令 → /api/voice/utter
  │        └─ 不 matched              → 丢弃（噪音 / 无关对话）
  ▼
前端状态机 AsstState **不变**，只把「listening → recording」的触发源
从 Vosk 回调换成「后端返回 matched」
```

### 为什么不做「停顿切分」

openclaw 用 `triggerPauseWindow`（0.55s 停顿）区分「光唤醒」与「唤醒+指令」，是因为它的识别器是**流式**的 —— 唤醒词一命中就要立刻决定是否开始采集。

本项目是**分段 ASR**，文本本身就带答案，VAD 分段天然覆盖两种情况：

| 说法 | VAD 行为 | 结果 |
|---|---|---|
| 「衍衡」→ 停顿 → 「查天气」 | 停顿处切成两段 | 第 1 段 = 唤醒词（command 空）→ 提示音 → 第 2 段是指令 |
| 「衍衡，查天气」不停顿 | 一段 | 转写含唤醒词 + 内容 → command = 「查天气」 |

**不实现停顿检测器**，省掉一整块复杂度。

---

## 接口

### `POST /api/voice/wake`

请求：`{ "audio_base64": "<16kHz mono WAV, base64>" }`（与 `/api/voice/transcribe` 同格式）

响应：

```json
{ "ok": true, "matched": true, "command": "帮我查天气", "text": "衍衡，帮我查天气。" }
```

| 字段 | 含义 |
|---|---|
| `text` | ASR 原始转写（审计与排障用，不改写） |
| `matched` | 是否命中唤醒词 |
| `command` | 唤醒词之后的内容；仅唤醒词命中时为空串 |

ASR 未配置或调用失败 → `{ "ok": false, "error": "..." }`，前端按「本段丢弃」处理。

---

## 唤醒词匹配

**放后端**（纯函数，可 pytest 单测；前端保持薄）。规则由实测数据驱动，不是猜的：

| 唤醒词 | 云端实测转写 | 匹配规则 |
|---|---|---|
| 洛吉斯 | `洛吉斯。` | 去标点/空白后**直接包含** |
| 衍衡 | `燕恒。` | **同音字容错**：衍→{衍,燕,演,眼,沿}，衡→{衡,恒,横,哼} |

规则细节：

1. **归一化**：去掉全部空白与中英文标点（实测云端会自行补句号）
2. **只在开头匹配**：唤醒词须出现在归一化文本的**开头**才算命中。
   —— `我昨天说衍衡那个事` 不应触发。
3. **切分**：命中后去掉唤醒词，剩余部分即 `command`（再去首尾标点）；剩余为空 → `command = ""`
4. **多唤醒词**：命中任一即可（配置项 `voice.wake_word.keywords`，已存在）
5. **不做模糊/拼音匹配**：仅同音字表，避免把无关语句拉进来

---

## 前端改动

**移除**（已逐个核实引用点）：

| 文件 | 说明 |
|---|---|
| `web/public/lib/wake-word.js` | Vosk WASM 引擎封装（含同音字表与变体表） |
| `web/public/lib/vosk.js` | Vosk 运行时库 |
| `web/public/models/vosk-model-small-cn-0.22.tar.gz` | 43MB 中文模型，**且是提交进 git 的** |
| `web/public/vosk-test.html` | 引擎自测页 |
| `web/index.html:7-8` | `<script src="/lib/vosk.js">` 与 `window.vosk = window.Vosk` |
| `web/src/types/vosk.d.ts` | 引擎全局类型声明 |
| `web/src/types/raw.d.ts` | 为 `?raw` 引入引擎源码而加的声明（引擎删了就没用了） |
| `useWakeWord.ts` | 引擎调用、`initWakeModel`、同音字表 |
| `useAssistant.ts` / `store.ts` | `wakeConfig.model_path`、模型加载进度等 Vosk 专属状态 |
| `__tests__/wakeEngineRestart.spec.ts`、`wakeKeywords.spec.ts`、`useWakeWord.spec.ts` | 随引擎一并删除或重写 |

**新增**：

- 常驻 VAD（AnalyserNode）+ 分段录音
- 调 `/api/voice/wake` 的客户端方法
- 「仅唤醒词」时播放提示音并开录指令；「唤醒词+指令」时直接发起 `/voice/utter`

**不变**：`AsstState` 状态机、录音时长上限、TTS 播报门控、`/voice/utter` 与 `/voice/answer` 全部照旧。

---

## 成本与隐私

- **VAD 是第一道闸**：只有疑似人声的片段才上传，不是持续推流
- **最短语音时长**：短促爆音不上传。新增 `vad.min_speech_ms`，缺省 `300`
- **上传节流**：两次上传之间的最小间隔。新增 `vad.upload_throttle_ms`，缺省 `500`
- **连续失败熔断**：连续 3 次失败则暂停上传并在界面提示，避免疯狂重试烧钱。阈值写死为 3，不做成配置（先观察实际表现再决定是否需要可调）
- 每次上传在 `data/audit.log` 记一笔（可据此统计调用量）

> 新增配置放在 `voice.vad` 段而非新建段：这三个都是「收听时序」参数，与既有的
> `silence_threshold` / `silence_duration_ms` / `max_duration_ms` / `answer_timeout_ms` 同族，
> 该段已有「同族参数放一起、不新增分段」的先例（见 `answer_timeout_ms` 的注释）。

> ⚠️ **隐私边界发生变化，必须写进 README 与设置页**：
> 从「音频**不出浏览器**」变为「**每次有人说话都会把该片段送到云端 ASR**（`api.xiaomimimo.com`），无论是否唤醒」。
> 这是本方案的明确代价，用户已知情选择。

---

## 错误与降级

| 情况 | 行为 |
|---|---|
| 云端 ASR 不可用 | 界面**明确提示**「唤醒不可用」，不静默失败；双击悬浮球手动触发仍可用 |
| 单次 ASR 超时/失败 | 丢弃该段，继续听 |
| 连续失败达阈值 | 暂停上传 + 提示（熔断） |

---

## 测试

**后端（pytest）**

- 匹配纯函数单测，**固化实测样本**（本次最有价值的回归资产）：
  - 正例：`燕恒。`、`洛吉斯。`、`洛吉斯，帮我查天气。`
  - 反例：`今天天气怎么样`、`我昨天说衍衡那个事`、`若缉私`、`也行`
- 切分单测：仅唤醒词 → `command=""`；唤醒词+内容 → 正确切分；带标点/空格
- 端点单测：mock ASR，验证 `matched`/`command`/错误分支

**前端（vitest）**

- VAD 起止判定、分段边界（mock AudioContext）
- 状态流转：matched 且 command 空 → `awaiting/recording`；matched 且有 command → 直接发起 turn
- 熔断与节流

**人工验收（必须做）**

- 真机喊「衍衡，帮我查天气」一句话走通
- 真机喊「衍衡」→ 停顿 → 说指令 走通
- 无关对话不误触发

---

## 风险

| 风险 | 说明 | 应对 |
|---|---|---|
| **合成音 ≠ 真人** | 上面所有实测用的是 SAPI 合成音。云端对**合成音**识别好，不代表对真人好 | 人工验收是硬门槛，不通过就不算完成 |
| 调用成本 | 每次有人说话都调用 | 人工验收时实测频率；熔断与节流可调 |
| 隐私边界变化 | 未唤醒时音频也上云 | 已确认接受；README 与设置页必须写明 |
| 误唤醒 | VAD 把无关对话送上去 | 只在开头匹配 + 需完整唤醒词；可通过最短时长调 |

---

## 后续子项目（不在本 spec 范围）

| # | 内容 | 依赖 |
|---|---|---|
| 2 | **本地 KWS**：sherpa-onnx KWS（zipformer-wenetspeech 3.3M，拼音自定义词，无需训练）。工程注意：WASM 单线程、线性内存只增不减（需 Web Worker + 空闲终止回收） | 子项目 1 |
| 3 | **本地 ASR**：sherpa-onnx ASR | 子项目 1 |
| 4 | **有序回退链 + 能力探测**：学 openclaw 的候选链（provider 优先、本地兜底、失败/超时逐个下移），能力探测不为探测加载模型 | 2、3 |

## 参考

- openclaw 语音唤醒与 ASR 设计（本机 `openclaw@2026.9.4`）：`docs/nodes/voicewake.md`、`docs/nodes/audio.md`、`docs/platforms/mac/voicewake.md`
- sherpa-onnx KWS 中文模型：`sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01`（ModelScope）
