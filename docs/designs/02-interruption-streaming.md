# 02 · 打断语义与句级流式播报

> 借鉴：Pipecat（InterruptionFrame + interruptible 白名单、未播文本不进上下文、Smart Turn）、
> RealtimeTTS（句级切割 + 预取 + 引擎 fallback）。优先级 P1。与 03 共用 speaking/回声护栏改动。

## 实施状态

- **全三批已完成（2026-09-29）**：
  - 批1：`useTts.stopSpeak`（清队/停合成/停 API Audio/作废代际）+ `currentAudio` 修叠播 bug
    + PanelHeader「停止朗读」与 TtsMini「停止」按钮 + `runTurn`/`sendAnswer` 接线；
  - 批2：`speech.ts splitSentences`（终结符断句/长句二分/短尾并入）+ 句队列泵
    （代际接管、同步复位保住既有测试契约）+ API 引擎窗口 2 预取 + 逐句浏览器回退 +
    `spokenChars` 计数（暂不消费）；
  - 批3：`voice.vad.barge_in` 配置（三处同步 + gen:api）+ 独立能量监控 `bargeIn.ts`
    （400ms 连续超阈触发、失败静默降级）+ 唤醒编排接线（命中 `stopSpeak('barge_in')`、
    余响由既有 1.2s 回声护栏拦截）+ 设置页开关。
- **与设计的偏差**：① 配置放 `voice.vad.barge_in` 而非 `voice.barge_in` ——
  `editable_snapshot` 只暴露 vad/wake_word 两个语音子段，放 voice 顶层前端收不到；
  ② 设计里「TtsMini 播放条」实际是设置迷你卡，停止按钮同时加在了 PanelHeader（真正的播报期 UI）。
- 测试：vitest 238 绿（新增 15：splitSentences 3 / 队列打断 6 / bargeIn 单元 3 / barge-in 集成 3）、
  pytest 494 绿、mypy 干净、vue-tsc/build 通过、gen:api 已重跑。

## 1. 现状（问题定位）

| # | 现状 | 位置 | 后果 |
|---|---|---|---|
| 1 | 播报 = **整段一个 utterance**（浏览器）/ 一次整段合成（API），无句级切割、无预取 | `web/src/composables/assistant/useTts.ts:127-154,159-186` | 长回复首响慢；无法只播一半 |
| 2 | **没有「停止朗读」能力**：唯一 cancel 点是下一次 `speakBrowser` 入口的 `speechSynthesis.cancel()`（`useTts.ts:130`）；API 引擎新 `Audio` **不停旧 Audio**（未保存引用） | `useTts.ts:130,159-186` | 用户无法主动掐断播报；API 引擎可能叠播 |
| 3 | 播报期间**麦克风整体释放**，语音无法打断 | `wakeOrchestrator.ts:691-695` | barge-in 完全缺失 |
| 4 | 新回合 `runTurn → abortController.abort()` 只清流，**不播打断 TTS**（onAbort 不动播报） | `useChat.ts:33,126-134` | 用户插话后旧播报继续念，与新回合叠音 |
| 5 | 没有打断优先级规则（哪些播报可断、哪些不可） | — | 改动无约束可依 |
| 6 | `speechForBlocks` 回合播报只在 `onDone` 触发，question 到达即播 | `web/src/blocks/speech.ts:62-76`、`useChat.ts:100-125` | 结构清晰，✅ 保持 |

**架构事实（决定设计边界）**：本项目 LLM 上下文 = 文本块（`ChatMessage.blocks`），**不是 TTS 转写**——pipecat「未播文本不进上下文」原则在这里天然成立，唯一要防的是将来把播报文本回写会话。故设计含一条「立测试钉住」的守则（§5）。

## 2. 目标行为

1. **可停**：任何播报可被停止（UI 按钮、新回合开始），API/Browser 双引擎统一语义。
2. **有白名单**：打断规则表驱动（§3.1），实现与测试都按表走。
3. **句级流式**：长文本切句逐播，API 引擎预取下一句，首响提前、失败逐句回退浏览器引擎。
4. **（阶段三）barge-in**：可配置开启「播报中听用户开口」，开口即停播转入作答/指令分流。
5. 播报中断不污染会话上下文（守则 + 测试）。

## 3. 设计

### 3.1 打断白名单（interruptible 矩阵）

| 播报来源 | 新回合 sendText | 停止按钮 | 语音 barge-in（阶段三） | 备注 |
|---|---|---|---|---|
| question（澄清/确认/完成追问） | ✅ 打断并立即处理作答 | ✅ | ✅（开口即停播，段进 pendingQuestion 通道） | 打断后 question 块按实际作答翻状态 |
| summary / 正文 text | ✅ 打断 | ✅ | ✅ | |
| notice / error | ✅ | ✅ | ✅ | |
| 提示音 beep | — | ❌ | ❌ | 固定 0.2s，不接打断链路 |
| 唤醒词命中提示音 | — | ❌ | ❌ | 同上 |

落地形式：`useTts` 增加 `stopReason: 'ui' | 'new_turn' | 'barge_in'` 参数（仅影响日志/审计口径），**不做按来源的拒绝停播**——白名单的价值在测试与后续演进有据可依；唯一硬规则是 beep 独立于 TTS 队列。

### 3.2 批次一：stopSpeak 统一打断（最小可用）

`useTts.ts` 改造：

```ts
let currentAudio: HTMLAudioElement | null = null;   // 修 API 引擎叠播 bug

function stopSpeak(reason = 'ui') {
  speakGen++;                        // 作废迟到 onend/onended
  window.speechSynthesis.cancel();   // browser 引擎
  if (currentAudio) { currentAudio.pause(); currentAudio.src = ''; URL.revokeObjectURL(...); currentAudio = null; }
  speakQueue = [];                   // 阶段二的句队列一并清空
  speaking.value = false;            // 立即复位（gen 判断兜底迟到回调）
}
```

**接线点**：
1. `useChat.runTurn` 开头（abort 旧流处）→ `stopSpeak('new_turn')` —— 修「插话后旧播报继续念」。
2. 迷你播放条 `TtsMini` 增加/校对停止按钮 → `stopSpeak('ui')`。
3. `speakApi` 每次开始前先 `stopSpeak`（或至少停 `currentAudio`）——修叠播 bug。
4. `onAbort` **不**停播（现状语义：取消流 ≠ 静音）——由 1 覆盖「新回合」场景，显式 `cancelTool` 场景播报允许播完（白名单第 4 行）。

### 3.3 批次二：句级流式播报

**切句**（`speech.ts` 新增纯函数 `splitSentences`，stripMarkdown 之后执行）：
- 分隔符：`。！？；\n` 及成对 `"` 结尾；
- 单句 >120 字 → 按 `,，` 二分；
- 尾句 <8 字 并入前句（避免孤字尾音）。

**浏览器引擎**：`speakText` 改为「入队 + 泵」——队列逐句 `SpeechSynthesisUtterance`，`onend` 触发下一句；`stopSpeak` 清队。`speaking` 在**队列排空**时才复位（保持「播报期间停麦 + 回声护栏按 speaking=false 武装」的现有语义不变）。

**API 引擎**：预取窗口 = 2 —— 当前句 `Audio` 播放时并发 `POST /api/tts` 预合成后续句子（按序缓存，乱序完成不乱播）；某句合成失败 → 该句回退 `speakBrowser`（现有 fail→browser 逻辑下沉到句级）；`Audio.onended` 泵队列。首句仍走现有 `stripMarkdown → speechForBlocks` 出口，**回合播报统一出口（summary.tts_text 优先）不变**。

### 3.4 批次三：barge-in（语音打断播报）

- 配置 `voice.barge_in: bool = false`（默认关；三处同步：`schema.py` voice 段 / `api/schemas.py` / `configDefs.ts`）。
- 开启时，`watch(speaking)` 不再无条件 `stopListening()`，改为切「监听-打断模式」：
  - 单独 `getUserMedia({echoCancellation:true, noiseSuppression:true, autoGainControl:true})` 流（与段录音器分离，避免 MediaRecorder 叠流冲突）；
  - 复用 `useSegmentRecorder` 的 RMS 轮询：阈值 = `silence_threshold × 2`，**连续 ≥400ms** 超阈 → 判定用户开口（比 VAD 起段更激进，专为打断）；
  - 命中 → `stopSpeak('barge_in')` + 记 `bargeInAt`；**停播后 300ms 内的音频段丢弃**（扬声器余响），随后恢复常规段处理（回声护栏照常按 speaking=false 武装 1200ms，两层护栏叠加）；
  - 用户未开口：播报结束 → 现有 `stopListening`/回声护栏/`question_ready` 流程全部保持。
- 白名单按 §3.1 执行；beep 不受影响。
- **失败回退**：取流失败/权限拒绝 → 自动降级为现状（停麦），记 warning，不影响播报。

### 3.5 「未播文本不进上下文」守则

- 现状已满足（上下文来自 `blocks`，非 TTS）。落地为两条硬约束：
  1. `stopSpeak` / barge-in **不得**修改 `messages`/`blocks`（不删已生成文本、不回写已播文本）；
  2. 立 vitest：中断播报后 `store.messages` 与块流 byte 级不变。
- 若未来做「播报历史」（语音渠道回读），只允许记录 `spokenChars` 前缀——本设计先埋 `spokenChars` 计数（阶段二句队列推进时累加），不消费。

## 4. 实施步骤

| 批次 | 内容 | 验收 |
|---|---|---|
| **批 1** | §3.2 stopSpeak + 三处接线 + `currentAudio` 修复 | 播报中点新回合不叠音；API 引擎不叠播；TtsMini 可停 |
| **批 2** | §3.3 切句 + 双引擎句队列 + 预取 | 300 字回复首响明显提前；逐句失败逐句回退 |
| **批 3** | §3.4 barge_in 配置 + 监听-打断模式 + §3.5 守则测试 | 开关开启时口头打断生效；关闭时行为与现状全同 |

## 5. 测试计划

- **vitest**：
  - `useTts.spec` 扩展：`stopSpeak` 清队/复位 speaking/作废迟到 onend；`currentAudio` 停止；句队列泵顺序；预取乱序不乱播；单句失败回退 browser。
  - 新增 `speech.splitSentences.spec`（纯函数：分隔/长句二分/尾句合并）。
  - 新增守则测试：`stopSpeak` 后 store 消息不变。
  - `useWakeWord.spec` 播报门控用例保持绿；barge-in 新增：开口停播、300ms 余响丢段、取流失败降级停麦。
- **pytest**：本设计后端仅新增 `voice.barge_in` 配置字段（schema 校验测试）。
- **手动**：`verify-voice.mjs` 台补「播报中说『停』/插话」场景（开/关 barge_in 各一遍）。
