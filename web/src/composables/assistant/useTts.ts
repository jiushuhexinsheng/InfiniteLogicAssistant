import { ref } from 'vue'

/** 语音播报（双引擎）。
 *  Voice broadcast (dual engine).
 *  engine='browser'：浏览器 speechSynthesis（本地语音，零配置）。Browser speechSynthesis (local voice, zero config).
 *  engine='api'    ：POST /api/tts（后端 OpenAI 兼容 TTS），失败自动回退浏览器。POST /api/tts (backend OpenAI compatible TTS), auto-fallback to browser on failure. */
export type TtsEngine = 'browser' | 'api'

/** TTS 设置接口。TTS settings interface. */
export interface TtsSettings {
  /** TTS 引擎类型。TTS engine type. */
  engine: TtsEngine
  /** 语音播报总开关（关 = 回复不朗读，仅文本展示）。Master voice broadcast switch (off = no reading, text display only). */
  speakEnabled: boolean
  /** 音量（0-1）。Volume (0-1). */
  volume: number
  /** 语速（0.1-10，仅浏览器引擎）。Speech rate (0.1-10, browser engine only). */
  rate: number
  /** 音调（0-2，仅浏览器引擎）。Pitch (0-2, browser engine only). */
  pitch: number
  /** 浏览器语音名（'' = 系统默认）。Browser voice name ('' = system default). */
  voiceName: string
  /** API 语音名（'' = 用后端配置的 voice）。API voice name ('' = use backend configured voice). */
  apiVoice: string
}

/** TTS 设置本地存储键。TTS settings local storage key. */
const STORAGE_KEY = 'xluo.tts'

/** MiMo 预置音色（mimo-v2.5-tts）；API 模式下拉提示，可自定义输入任意名字。
 *  MiMo preset voices (mimo-v2.5-tts); API mode dropdown suggestions, can custom input any name. */
export const API_VOICE_SUGGESTIONS = ['Chloe', 'Mia', '冰糖', '茉莉', '苏打', '白桦', 'Dean', 'Milo', 'mimo_default']

/** 数值钳制工具函数。Number clamping utility function.
 *  @param n - 输入数值。Input number.
 *  @param min - 最小值。Minimum value.
 *  @param max - 最大值。Maximum value.
 *  @returns 钳制后的数值。Clamped number. */
function clamp(n: number, min: number, max: number) {
  if (!Number.isFinite(n)) return min
  return Math.min(max, Math.max(min, n))
}

/** 从本地存储加载 TTS 设置。Load TTS settings from local storage.
 *  @returns TTS 设置对象。TTS settings object. */
function load(): TtsSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const p = JSON.parse(raw)
      return {
        engine: p.engine === 'api' ? 'api' : 'browser',
        speakEnabled: p.speakEnabled !== false,
        volume: clamp(p.volume ?? 1, 0, 1),
        rate: clamp(p.rate ?? 1, 0.1, 10),
        pitch: clamp(p.pitch ?? 1, 0, 2),
        voiceName: typeof p.voiceName === 'string' ? p.voiceName : '',
        apiVoice: typeof p.apiVoice === 'string' ? p.apiVoice : '',
      }
    }
  } catch { /* 解析失败则用默认。Parse failure: use defaults. */ }
  return { engine: 'browser', speakEnabled: true, volume: 1, rate: 1, pitch: 1, voiceName: '', apiVoice: '' }
}

/** 全局单例设置（全站共享；滑块/下拉直接改它，下次播报即生效）。
 *  Global singleton settings (site-wide shared; sliders/dropdowns directly modify it, effective on next broadcast). */
export const ttsSettings = ref<TtsSettings>(load())

/** 是否正在播报。门控唤醒引擎用：播报期间暂停监听，避免助手自己的声音自触发唤醒。
 *  Whether speech is currently playing. Used to gate the wake engine: listening is paused
 *  during playback so the assistant's own voice cannot self-trigger the wake word. */
export const speaking = ref(false)

/** 播报代际：连续播报时，旧播报迟到的 onend 不得复位新一轮的 speaking。
 *  Playback generation: with back-to-back utterances, a late onend from an older
 *  utterance must not clear the newer one's speaking flag. */
let speakGen = 0

/** 保存 TTS 设置到本地存储。Save TTS settings to local storage. */
export function saveTts() {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(ttsSettings.value)) } catch { /* ignore */ }
}

/** 语音播报总开关：关 = 回复不朗读（试听按钮仍可手动播放）。
 *  Master voice broadcast switch: off = no reading (preview button still works manually). */
export function toggleSpeak() {
  ttsSettings.value.speakEnabled = !ttsSettings.value.speakEnabled
  saveTts()
}

/** 可用浏览器语音（中文优先，其余兜底）。
 *  Available browser voices (Chinese first, others as fallback).
 *  @returns 语音列表，中文在前。Voice list, Chinese first. */
export function getVoices(): SpeechSynthesisVoice[] {
  if (typeof window === 'undefined' || !window.speechSynthesis) return []
  const all = window.speechSynthesis.getVoices()
  const zh = all.filter(v => /^zh/i.test(v.lang))
  const others = all.filter(v => !/^zh/i.test(v.lang))
  return [...zh, ...others]
}

/** 语音列表异步就绪时回调（部分浏览器需等 voiceschanged 事件）。
 *  Callback when voice list is asynchronously ready (some browsers need to wait for voiceschanged event).
 *  @param cb - 就绪回调函数。Ready callback function. */
export function loadVoices(cb: () => void) {
  if (typeof window === 'undefined' || !window.speechSynthesis) return
  const s = window.speechSynthesis
  s.getVoices()
  s.onvoiceschanged = () => cb()
  cb()
}

/** 解析当前设置对应的浏览器语音。Resolve browser voice for current settings.
 *  @returns 匹配的语音对象，或 undefined。Matched voice object, or undefined. */
function resolveVoice(): SpeechSynthesisVoice | undefined {
  const vs = getVoices()
  if (!vs.length) return undefined
  const name = ttsSettings.value.voiceName
  if (name) return vs.find(v => v.name === name)
  return vs.find(v => /^zh/i.test(v.lang) && v.localService)
    || vs.find(v => /^zh/i.test(v.lang))
    || vs[0]
}

/** 浏览器语音播报。Browser voice broadcast.
 *  @param text - 要播报的文本。Text to broadcast. */
function speakBrowser(text: string) {
  if (typeof window === 'undefined' || !window.speechSynthesis) return
  try {
    window.speechSynthesis.cancel()
    const u = new SpeechSynthesisUtterance(text.replace(/\n/g, '，'))
    const s = ttsSettings.value
    u.volume = s.volume
    u.rate = s.rate
    u.pitch = s.pitch
    const v = resolveVoice()
    if (v) { u.voice = v; u.lang = v.lang } else { u.lang = 'zh-CN' }
    // 代际计数：只有本轮播报的结束回调才允许复位 speaking。
    // 上一轮被 speechSynthesis.cancel() 打断时其 onend 可能迟到，若不加代际会把
    // 新一轮的 speaking 提前置 false，导致门控提前放行、麦克风被助手声音自触发。
    // Generation counter: only this round's completion callback may clear speaking. When
    // a previous utterance is cut off by speechSynthesis.cancel() its onend may arrive
    // late; without the counter it would clear the new round's flag early, reopening the
    // mic while the assistant is still speaking.
    const gen = ++speakGen
    speaking.value = true
    const done = () => { if (gen === speakGen) speaking.value = false }
    u.onend = done
    u.onerror = done
    requestAnimationFrame(() => {
      try { window.speechSynthesis.speak(u) } catch { /* ignore */ }
    })
  } catch { /* ignore */ }
}

/** API 语音播报（后端 OpenAI 兼容 TTS）；失败自动回退浏览器。
 *  API voice broadcast (backend OpenAI compatible TTS); auto-fallback to browser on failure.
 *  @param text - 要播报的文本。Text to broadcast. */
async function speakApi(text: string) {
  try {
    const res = await fetch('/api/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, voice: ttsSettings.value.apiVoice || undefined }),
    })
    if (!res.ok) throw new Error(`TTS HTTP ${res.status}`)
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const audio = new Audio(url)
    audio.volume = ttsSettings.value.volume
    // 与 speakBrowser 同样的代际计数：回退到 speakBrowser 时后者会再 ++speakGen 并自己
    // 置 speaking = true，故先 done() 再回退不会闪断。
    // Same generation counter as speakBrowser: when falling back, speakBrowser bumps the
    // generation again and sets speaking itself, so calling done() first does not flicker.
    const gen = ++speakGen
    speaking.value = true
    const done = () => { if (gen === speakGen) speaking.value = false }
    const fail = () => { done(); URL.revokeObjectURL(url); speakBrowser(text) }
    audio.onended = () => { done(); URL.revokeObjectURL(url) }
    audio.onerror = fail
    await audio.play().catch(fail)
  } catch (e) {
    console.warn('[TTS] API 播报失败，回退本地语音:', e)
    speakBrowser(text)
  }
}

/** 按当前引擎播报。Broadcast by current engine.
 *  @param text - 要播报的文本。Text to broadcast. */
export function speakText(text: string) {
  if (!text || typeof window === 'undefined') return
  if (ttsSettings.value.engine === 'api') {
    void speakApi(text)
  } else {
    speakBrowser(text)
  }
}

/** 自动播报入口：总开关为关时不发声（区别于「试听」的强制播放）。
 *  Auto broadcast entry: no sound when master switch is off (different from "preview" forced playback).
 *  @param text - 要播报的文本。Text to broadcast. */
export function speakAuto(text: string) {
  if (ttsSettings.value.speakEnabled) speakText(text)
}

/** 试听当前设置。Preview current settings. */
export function testVoice() {
  speakText('你好，我是小逻。这样调整的音量和声音可以吗？')
}

/** TTS 管理 composable。TTS management composable.
 *  @returns 包含 TTS 设置、保存、语音列表、播报等方法的接口。Interface containing TTS settings, save, voice list, broadcast methods etc. */
export function useTts() {
  return { ttsSettings, speaking, saveTts, getVoices, loadVoices, speakText, testVoice, speakAuto, toggleSpeak }
}
