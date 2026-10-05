# 通话模式（无唤醒词持续流转 + 三级判定漏斗）设计

## 背景：为什么要做

现有语音链路必须念唤醒词（「衍衡」/「洛吉斯」）才能触发：浏览器 VAD 切段 → 本地 KWS 闸门 → 云端 ASR → 编排。目标体验是**豆包通话模式**：双击球进入通话，不念任何词，直接开口说，系统判断「这句话是不是对我说的」，AI 说完可随时插话打断，可连续多轮追问。

业界调研结论（2026-10，来源见文末）：

- 字节 SeedRealtime（豆包通话模式底层）靠端到端模型内生的「该接话时接话、该沉默时沉默 + 分辨旁人闲聊」；闭源，不可用。
- 开源/自研管线的主流做法是**三层叠加**：会话态假设（进入通话即默认对我说的候选）+ 端点检测（说完没）+ 语义闸门（该不该回）。EMNLP 2026 综述 DuplexSurvey 把它形式化为 L0 外部规则 / L1 sidecar 小模型 / L2 模型内决策，其中 **L1 sidecar 是工业界主流**。
- 关键取舍（用户已确认）：**双模式并存**（唤醒链保留）、**混合式**（本地粗筛 + 云端精转，粗筛全本地零成本）、**持续对话 + 可打断**（不做端到端全双工）。

## 目标

1. 双击悬浮球进入/退出通话模式，免唤醒词直接说话
2. 本地漏斗把 80%+ 段落挡在云端之外，云端只为疑似命中段付费
3. AI 播报期间开口即打断（barge-in），回答完成后开放窗口内可连续追问
4. 唤醒词链路原样保留（入口从双击挪到面板）

## 非目标

- 真全双工（边听边说重叠也自然，需 Moshi 类端到端模型）——不做
- WebSocket 常流音频上行——不做，复用段落式
- pipecat / LiveKit 框架整体引入——不做，只按件采购 Smart Turn
- 多人声纹/说话人识别——浏览器单麦场景不存在这条退路

---

## 架构

### 通道：复用段落式，不改 WS

浏览器 VAD 已把音频切段（`useSegmentRecorder`：1.5s 静音 / 10s 上限），回声护栏、TTS 状态、既有测试都围绕「段」构建。通话模式下**段落采集方式完全不变**，只是段的去向从 KWS 快检换成判定漏斗。

### 三级判定漏斗（服务端，每段依次过）

```
段落 POST /voice/call/segment (base64 wav)
  │
  ├─ L0 确定性粗筛（规则，零成本，预计丢弃 80%+ 段落）
  │    · 通话会话未激活 → 丢
  │    · TTS 回声护栏窗口内（复用 ECHO_GUARD_MS=1200 语义）→ 丢
  │    · tab 无焦点（前端随段上报 document.hasFocus()）且不在开放窗口期 → 丢
  │    · 段落 RMS 能量过低 / 时长 < 0.5s → 丢
  │
  ├─ L1 本地粗转写（sherpa-onnx，CPU，零云端）
  │    · get_local_asr()：streaming zipformer 中英双语（bilingual-zh-en-2023-02-20，
  │      官方 RTF 0.108/2 线程，Apache-2.0，cp314 win wheel 现成）
  │    · 转写文本过词表/规则快筛（句首称呼、祈使句式；明显闲聊/零碎 → 丢）
  │    · Smart Turn v3（pipecat-ai/smart-turn，ONNX int8 8MB，CPU 10-65ms，
  │      23 语言含中文，BSD-2）复核「说完没」——区分真说完与思考长停顿
  │
  └─ L2 云端精判（只为疑似命中的少数段付费）
       · 云端 ASR 精转写：复用现有 /voice/transcribe 通道（审计 audio-upload 口径不变）
       · LLM 意图闸门：现有 LLM profile 一次短 prompt 分类
         输入 = 精转写文本 + 近几轮上下文 + 焦点/窗口元数据
         输出 = 结构化判定 { 指令 / 闲聊 / 旁人说话 / 无法确定 }
       · 指令 → 进现有 /voice/utter 编排 pipeline（澄清/确认/执行/SSE 全复用，零改动）
       · 其余 → 静默丢弃 + audit 记 call-funnel miss
```

**声音检查的物理链**：RMS 能量（有没有人说话，`v=(byte-128)/128`，`RMS=√(Σv²/N)`，AnalyserNode 100ms 轮询）→ 本地流式 ASR（说了什么）→ Smart Turn（说完没）→ 云端 LLM（是不是对我说的）。**模型共三个：sherpa-onnx zipformer、Smart Turn v3、现有云端 LLM，无新增云端依赖。**

### 模式互斥与入口

- **双击悬浮球 = 通话开关**（待机 ⇄ 通话）。状态胶囊文案改「双击开通话 / 通话聆听中…」（`useAssistantVisuals.ts` 映射表同步改）。单击展面板、拖拽、250ms 单双击消歧（`FloatBall.vue`）不动。
- **唤醒词模式降级为面板开关**（`AssistantPanel`），配置项 `voice.mode` 记住上次选择。唤醒链代码与测试不动。
- 两条链互斥：通话模式激活时 KWS 闸门暂停；`call/stop` 后恢复。

### 开放窗口（follow-up）

回答完成 → 开放窗口（`voice.call.open_window_s`，默认 8s）：窗口内段落漏斗放宽（免 tab 焦点），鼓励连续追问；窗口过期回到严格粗筛。等价 Alexa follow-up mode 的做法。

### 打断（barge-in）

AI 播报期间从「停麦」改为「开监控」：复用 `startBargeInMonitor`（RMS 阈值 = silence_threshold × 2，连续超阈 400ms）→ 触发 `stopSpeak('barge_in')` + 经 `StopController` 取消进行中的 LLM 流 → 新段落立即进漏斗。播报余响由既有回声护栏（ECHO_GUARD_MS=1200）兜底。

---

## 组件与文件级改动

### 后端新增

| 文件 | 职责 |
|---|---|
| `core/api/voice/call.py` | 路由 `POST /voice/call/start`、`/voice/call/stop`、`/voice/call/segment`；段落进漏斗的编排入口。审计补丁点 `core.api.voice.call.audit`（沿用命名空间约定） |
| `core/voice/call_funnel.py` | 漏斗纯逻辑 `funnel(segment, session_state) -> Verdict`：L0 规则、L1 词表快筛、L2 调用编排，全部依赖注入可假件测试 |
| `core/voice/local_asr.py` | `get_local_asr()` 单例封装 sherpa-onnx streaming zipformer（模式同 `kws.py`）；加载失败 `available=False`，漏斗降级跳过 L1 转写并记 warn |
| `core/config/schema.py` | 新增 `voice.call` 段：`enabled`、`open_window_s`（默认 8）、`l0_min_rms`、`l0_min_seconds`（默认 0.5）、`smart_turn_enabled`、`local_asr_model` |
| `core/prompts.py` | L2 意图闸门 prompt（结构化输出四分类） |
| `models/` | streaming zipformer 中英模型入库（KWS 模型已入库先例，走同一策略） |

### 后端复用（不改或微改）

- `/voice/transcribe`：L2 精转写直接复用，审计口径不变
- `pipeline.py` / `/voice/utter`：命中后走现有编排，**零改动**
- `control.py`：打断取消复用
- Smart Turn：`pip install pipecat-ai`（或仅 smart-turn ONNX 件），加载失败降级为「浏览器 VAD 切段即回合边界」（现状手感）
- `core/llm/client.py`：L2 闸门走现有重试/熔断/failover

### 前端改动

| 文件 | 改动 |
|---|---|
| `composables/assistant/callMode.ts`（新） | 通话 FSM：`idle → listening → responding`，开放窗口计时，与唤醒链互斥启停 |
| `useWakeWord.ts` / `wakeOrchestrator.ts` | 段落分发按模式路由：唤醒模式走原 KWS 链，通话模式走 `postCallSegment` |
| `FloatingAssistant.vue` + `useAssistantVisuals.ts` | 双击语义改为通话开关；状态胶囊文案 |
| `AssistantPanel.vue` | 加唤醒词模式开关 |
| `useChat` / `useTts` | 通话模式下播报期启用 barge-in 监控而非停麦（`bargeIn.ts` 本身不改） |
| `api.ts` | 加 `startCall` / `stopCall` / `postCallSegment`；SSE 事件复用现有 13 类，漏斗决策只进 audit 不新增前端事件 |

### 类型同步

`call.py` 响应走 pydantic `response_model` → `gen_openapi` → `generated.ts`（CI 既有校验流程）。

---

## 错误处理与降级

每一级都必须「坏得静默、链路不断」：

1. **本地 ASR 加载失败/模型缺失** → L1 跳过，只走 L0+L2（功能可用、成本略升）。记 warn + `python main.py check` 报告
2. **Smart Turn 加载失败** → 以浏览器 VAD 静音切段为回合边界（现状行为），记 warn
3. **L2 云端 ASR/LLM 失败** → 该段按未命中静默丢弃 + audit 记 `call-funnel error`，不打断会话不弹错
4. **漏斗误杀（该回没回）** → 开放窗口内连续 N 段（默认 2）未命中时，对最后一段**重跑 L2 闸门且置 `relax=true`**（prompt 提示「宁可误报不可漏报」），命中即处理；audit 全程留痕供事后调参
5. **回声自触发** → TTS 播报期 L0 硬丢 + 回声护栏 1.2s + barge-in 触发后武装护栏，三层
6. **会话泄漏** → `call/stop` 与页面卸载都关会话；后端无段落 5 分钟自动过期

## 配置（config.yaml）

```yaml
voice:
  call:
    enabled: true
    open_window_s: 8
    l0_min_rms: 0.02        # 段落 RMS 低于此视为非人声（具体值实现期用真音频标定）
    l0_min_seconds: 0.5
    smart_turn_enabled: true
    local_asr_model: models/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20
```

密钥不涉及（L2 复用既有 profile 密钥）。

## 测试策略（TDD，先写测试）

- **pytest**：
  - `test_call_funnel.py`：L0 每条规则、L1 词表快筛、L2 降级路径、端到端（假 ASR/假 LLM 注入，模式同现有 `asking_policy` 夹具）
  - `test_local_asr.py`：单例、不可用降级
  - `test_call_api.py`：三个端点、审计行、会话过期
- **双端夹具**：仿 `tests/data/wake_vectors.json` 建 `tests/data/call_funnel_vectors.json`（段落特征描述 + 文本用例 → 期望漏斗决策），pytest 与 vitest 共享
- **vitest**：通话 FSM 状态迁移、开放窗口计时、与唤醒链互斥、barge-in 通话模式接 `stopSpeak`、双击语义切换
- **mypy**：新模块纳入 `mypy core/` 既有范围
- **验收**：`npm run verify:voice` 加通话模式脚本（无证据一律 INCONCLUSIVE）

## 里程碑（供实施计划拆解）

1. **M1 漏斗骨架**：`call_funnel.py` L0 + 三端点 + 会话状态，前端双击路由 + FSM（此时 L1/L2 全假件）——可端到端跑通但全靠云端
2. **M2 本地 L1**：`local_asr.py` + 模型入库 + 词表快筛 + Smart Turn 接入与降级
3. **M3 云端 L2 + 打断**：意图闸门 prompt + 开放窗口 + barge-in 接线 + 误杀兜底
4. **M4 验收收尾**：夹具全绿、verify:voice 脚本、文档同步（README/wiki/updates）

## 业界来源

- DuplexSurvey（EMNLP 2026）：arxiv.org/abs/2606.19453、github.com/MM-Speech/DuplexSurvey
- 字节 SeedRealtime（豆包通话模式）：seed.bytedance.com/zh/blog/seedrealtime-audio-visual-full-duplex-llm-released-toward-omni-modal-natural-interaction
- pipecat Smart Turn：github.com/pipecat-ai/smart-turn（BSD-2）；docs.pipecat.ai Smart Turn / FilterIncompleteUserTurns 文档
- sherpa-onnx streaming zipformer：github.com/k2-fsa/sherpa-onnx；模型 RTF 表 k2-fsa.github.io/sherpa/onnx/pretrained_models/online-transducer/
- LiveKit TurnDetector：docs.livekit.io/agents/logic/turns/turn-detector/
- OpenAI Realtime server_vad/semantic_vad 规格：github.com/openai/openai-openapi
- ASCIL（post-ASR 二次判定层，与 L2 同构）：arxiv.org/abs/2609.12469
- Moshi（全双工参照，本期不做）：github.com/kyutai-labs/moshi
