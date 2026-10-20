# 09 · 流式语音与 sherpa-onnx 本地引擎

2026-10-19。目标：把语音链路改为 **一条 WebSocket 流**（麦克风 → 本地 VAD → KWS → ASR →
partial/final），四个能力各自可选本地/API，本地统一走 sherpa-onnx；模型按能力分目录，
每个模型可独立选 CPU/GPU。

## 已落地的决策

1. **没有云端 VAD**：VAD 只在本机（TEN VAD / Silero）；模型缺失时会话明确报错。
2. **硬件范围**：浏览器输入/输出设备 + 每个本地模型独立的 `provider`（cpu/cuda/coreml）与线程数。
3. **不再保留旧切段上传链路作为回退**（真实浏览器全部走流式；旧代码的删除见文末「待清理」）。
4. **本期不接本地 LLM**：`models/llm/` 仅预留，LLM 仍走 API。

## 目录

```text
models/
  vad/     ten-vad.onnx / silero_vad.onnx
  kws/     sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01/
  asr/     sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23/
           sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20/
  tts/     kokoro-multi-lang-v1_1/
  llm/     预留（本期不接线）

core/voice/local/sherpa_onnx/
  registry.py   扫描/校验/推断 family 与 streaming；不加载模型
  audio.py      PCM/WAV、重采样、RMS、分帧
  hardware.py   provider 可用性、默认线程、ProviderUnavailableError
  vad.py        TEN VAD / Silero
  kws.py        Zipformer KWS（关键词文件写到 data/generated/kws）
  asr.py        Zipformer / 其它在线 sherpa ASR
  tts.py        Kokoro OfflineTts

core/voice/local/runtime.py     四类引擎的懒加载单例（配置热重载后重建）
core/voice/streaming/session.py 每连接会话：分段、partial、final、wake
core/api/voice/stream.py        /api/voice/asr/stream WebSocket
core/api/voice/models.py        模型列表 / 刷新 / 硬件 / 能力快照
```

## WebSocket 协议

端点：`/api/voice/asr/stream`（Vite 开发代理需 `ws: true`）。

客户端 → 服务端：

- 首条 JSON：`{"type":"start","sample_rate":16000,"channels":1,"format":"pcm_s16le"}`
- 二进制：PCM16LE 帧（默认 20 ms）
- 控制：`mute` / `unmute`（TTS 回声）、`flush`、`cancel`、`stop`、`ping`

服务端 → 客户端：

- `ready`：`{mode, streaming, sample_rate, vad, kws, tts}`
- `vad`：`speech_start` / `speech_end`（含 `segment_id`、时长）
- `status`：`recognizing`
- `partial`：`{segment_id, text}`（本地流式 ASR 才有）
- `final`：`{segment_id, text, engine, fallback, reason, duration_ms, rms, wake}`
- `error` / `done` / `cancelled`

`final.wake` 是服务端合成的唤醒结论：`{matched, command, keyword, source, text}`，
其中 `source = kws | text`。前端据此走作答/通话/指令/续聊/唤醒分流，不再上传音频。

## 前端双缓冲

- `storeTranscript.liveTranscript`：`interim`（正在识别）与 `finalText`/`status`。
- 中间稿在状态栏（`StatusPill` 的「正在识别…」）与迷你条（`MiniPlayer`）显示；
  控制台聊天区末尾渲染 `InterimBubble`（虚线、光标动画）。
- 定稿：清中间稿 → `statusLine='识别完成'` 约 1.5 s → 被消费的文本进入聊天记录；
  未唤醒的旁白短暂显示为 ghost（「未进入对话」）。

## 配置

```yaml
voice:
  streaming: { enabled: true, frame_ms: 20, partial_interval_ms: 120,
               endpoint_silence_ms: 700, max_utterance_ms: 15000 }
  vad:
    mode: local                 # local | off（没有 api）
    engine: ten-vad
    model: models/vad/ten-vad.onnx
    vad_threshold: 0.5
    provider: cpu               # 每个模型独立
    num_threads: 0
  kws:
    mode: local                 # local | api（文本拼音）| off
    model_dir: models/kws/...
    provider: cpu
  asr:
    mode: local                 # local | cloud | hybrid
    streaming: true
    local_model: models/asr/...
    provider: cpu
  tts:
    mode: api                   # local | api
    local_model: models/tts/kokoro-multi-lang-v1_1
    provider: cpu
  hardware:
    input_device: ""
    output_device: ""
    echo_cancellation: true
    noise_suppression: true
    auto_gain: true
```

## 设置页信息结构

语音相关设置只有一个左侧入口「语音」，内部六个 Tab：

- **概览**：四能力状态灯（VAD/KWS/ASR/TTS）、当前模型/provider、一键本地、刷新模型。
- **唤醒**：唤醒开关/唤醒词/灵敏度、等指令窗、续聊窗口、聆听空闲、打断播报。
- **识别**：VAD/KWS/ASR 本地模式、模型下拉、CPU/GPU、阈值/线程/流式开关；下方是
  云端 ASR API Profile（只配 API）。
- **合成**：浏览器 / 本地 Kokoro / API 三选一；按选择显示浏览器语音、Kokoro 模型参数
  或 API Profile。
- **硬件**：输入/输出设备、回声消除/降噪/自动增益。
- **高级**：WebSocket 流式开关、帧长、partial 间隔、端点静音、最长语音。

旧的「语音识别 / 语音合成 / 语音唤醒 / 本地模型」四个菜单已合并，避免同一能力多处配置。

## 模型获取

```bash
python scripts/fetch_models.py --kind vad
python scripts/fetch_models.py --kind asr --model sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23
python scripts/fetch_models.py --kind tts
```

KWS 小模型随仓库提供；`scripts/fetch_local_asr_model.py` 保留兼容，目标已改为
`models/asr/...`。`fetch_models.py` 对完整模型（Kokoro）保留 tarball 内的相对目录结构，
否则 `espeak-ng-data/` 会被平铺掉、registry 判模型不完整。

### 本地 TTS 的 Windows 细节

- **子进程生成**：sherpa Kokoro 在非主线程生成中文会只输出极短音频（espeak/词典的
  线程相关状态），所以 `core/voice/tts.py` 用单 worker `ProcessPoolExecutor`，主线程生成、
  模型在子进程常驻，不阻塞事件循环。
- **ASCII espeak 路径**：espeak-ng 在 Windows 上打不开含中文的项目路径，会回退到
  `/usr/share/espeak-ng-data` 并失败；`tts.py` 把 `espeak-ng-data` 复制到
  `%PUBLIC%\InfiniteLogicAssistant\espeak-ng-data` 后传入。
- `lang` 保持空串，交给多语种 lexicon/拼音；传 `multi` 会被 espeak 当成不存在的 voice。

## 验证

- `python -m pytest -q` → 685 passed
- `npm --prefix web test` → 404 passed
- `npm --prefix web run build` → vue-tsc + vite build 通过
- 真实浏览器（Chrome + fake audio）冒烟：状态栏「正在识别…」、迷你条持续更新中间稿，
  截图见 `tmp/stream-smoke-1.png`（本地临时产物，不入库）。

## 旧链路清理（2026-10-20 完成）

旧切段上传链路已整体删除：

- 后端：`/voice/transcribe`、`/voice/wake(/check)`、`/voice/call/segment`、
  `asr_dispatch.py`、`local_asr.py`、`kws.py`、`smart_turn.py`；`pipecat-ai` 依赖移除。
- 前端：`segmentFlow.ts`、`useSegmentRecorder.ts`、`wakeChain.ts`、`cloudAsrProvider.ts`、
  `webSpeechProvider.ts`、`localResult.ts`、`audio.ts`（blob→WAV）与 Web Speech 模式；
  手动验收脚本 `web/scripts/verify-voice.mjs` 同步删除。
- 测试：旧 wake 审计、ASR 分发、段录音器、通话段落漏斗用例删除；
  保留 `call_funnel.py` 的 L0/文本快筛/L2 判定（供 `/voice/call/judge`），
  新增 `/voice/asr/stream` 与会话单测。
- 上传成本口径：`audio-upload via=` 只剩 `stream`。
