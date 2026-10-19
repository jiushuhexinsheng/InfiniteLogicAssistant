import { computed, ref } from 'vue'
import type { WakeWordConfig, VadConfig, CallConfig } from '../../types'

/** 唤醒词配置（init 时从 /api/config 用 Object.assign 原地合并，保持引用稳定）。
 *  Wake word config (merged in-place from /api/config during init using Object.assign to keep reference stable).
 *
 *  model_path 是 Vosk 时代的遗留字段（唤醒改走云端判定后前端已无人读它）：留空串只是满足生成
 *  类型的必填字段，与后端 api schema 的同名默认值（`model_path: str = ""`）一致。
 *  model_path is a leftover from the Vosk era (nothing on the frontend reads it since the wake
 *  judgement moved to the cloud): the empty string only satisfies the generated type's required
 *  field, matching the backend api schema's default (`model_path: str = ""`). */
export const wakeConfig: WakeWordConfig = { enabled: true, keywords: ['衍衡', '洛吉斯'], sensitivity: 0.5, model_path: '' }
/** VAD（语音活动检测）配置。VAD (Voice Activity Detection) configuration. */
export const vadConfig: VadConfig = {
  mode: 'local',
  engine: 'ten-vad',
  model: 'models/vad/ten-vad.onnx',
  vad_threshold: 0.5,
  window_size: 0,
  provider: 'cpu',
  device: 0,
  num_threads: 0,
  silence_threshold: 0.02,
  silence_duration_ms: 1500,
  max_duration_ms: 10000,
  answer_timeout_ms: 8000,
  min_speech_ms: 300,
  upload_throttle_ms: 500,
  barge_in: false,
  followup_window_ms: 6000,
  listen_idle_s: 180,
}
/** 通话模式配置（/api/config 的 call 段覆盖默认值）。Call-mode config (the `call` block of /api/config overrides these defaults). */
export const callConfig: CallConfig = { enabled: true, open_window_s: 8, l0_min_rms: 0.02, l0_min_seconds: 0.5, smart_turn_enabled: true, local_asr_model: '', merge_l2: false, session_ttl_s: 300, relax_after_misses: 2 }

/** 浏览器硬件选项（输入/输出设备与麦克风处理）。Browser hardware options. */
export interface HardwareConfig {
  input_device: string
  output_device: string
  echo_cancellation: boolean
  noise_suppression: boolean
  auto_gain: boolean
}

/** 硬件配置默认值（/api/config 的 hardware 段覆盖）。Hardware defaults (overridden by /api/config). */
export const hardwareConfig: HardwareConfig = {
  input_device: '',
  output_device: '',
  echo_cancellation: true,
  noise_suppression: true,
  auto_gain: true,
}

/** 流式语音开关（/api/config 的 streaming 覆盖）。Streaming switch (overridden by /api/config). */
export const streamingEnabled = ref(true)
/** 通话激活标志：唯一事实来源（store 级，避免 wakeOrchestrator ↔ callMode 循环导入）。Call-active flag: store-level single source of truth (avoids a wakeOrchestrator ↔ callMode import cycle). */
export const callActive = ref(false)
/** 通话开放窗口截止时刻（毫秒时间戳；0 = 不在窗口内）。Call-open-window deadline (ms timestamp; 0 = outside the window). */
export const callWindowUntil = ref(0)

/** 是否在开放窗口内（回答播报结束后 open_window_s 秒，段落 meta.in_open_window 由路由读取上报）。Whether inside the open window (open_window_s seconds after playback ends; the segment router reads this into meta.in_open_window). */
export function inOpenWindow(): boolean {
  return Date.now() < callWindowUntil.value
}

/** 回答播报结束时调用：开开放窗口。Called when playback ends: opens the window. */
export function markTurnEnded(): void {
  callWindowUntil.value = Date.now() + callConfig.open_window_s * 1000
}

/** 通话态是否应开 barge-in 监控：通话激活时强制开（spec：通话模式播报期开监控而非停麦）。 */
export function callBargeInEnabled(configFlag: boolean, active: boolean = callActive.value): boolean {
  return active || configFlag
}

/** 响应式唤醒词列表（**可多个**，命中任意一个即唤醒）。Reactive wake keywords (plural; any hit wakes). */
export const wakeKeywords = ref<string[]>([...(wakeConfig.keywords ?? [])])

/**
 * 唤醒词的展示文案，供 UI 提示与状态文案使用，形如「衍衡」或「洛吉斯」。
 *
 * 由列表算出而非另存一个字符串：否则「界面提示的词」与「真正能唤醒的词」会有两份来源，
 * 改了配置忘改文案就会出现「按提示说却唤不醒」。
 *
 * Display text for the wake keywords, e.g. 「衍衡」或「洛吉斯」. Derived from the list rather
 * than stored separately: two sources of truth would let the on-screen hint drift from what
 * actually wakes the engine, producing "I said exactly what it told me and nothing happened".
 */
export const wakeHint = computed(() => wakeKeywords.value.map(k => `「${k}」`).join('或'))
