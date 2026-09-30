import { ref } from 'vue'
import { splitSentences } from '../../blocks/speech'

/** 语音播报（双引擎，句级队列）。
 *  Voice broadcast (dual engine, sentence queue).
 *  engine='browser'：浏览器 speechSynthesis（本地语音，零配置）。Browser speechSynthesis (local voice, zero config).
 *  engine='api'    ：POST /api/tts（后端 OpenAI 兼容 TTS），逐句失败回退浏览器。
 *                    POST /api/tts (backend OpenAI compatible TTS), per-sentence fallback to browser.
 *  长文本先经 splitSentences 切句入队，逐句播放：首响提前、可随时 stopSpeak 打断；
 *  API 引擎按窗口 2 预取后续句子（乱序完成按序播放）。
 *  Long text is split into sentences and queued: earlier first audio, interruptible
 *  via stopSpeak at any time; the API engine prefetches with a window of 2 (out-of-
 *  order completion, in-order playback). */
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

/** API 引擎预取窗口（当前句播放时预取后续 N 句）。API engine prefetch window (N upcoming sentences). */
const PREFETCH_WINDOW = 2

/** 单句播放兜底超时（毫秒）：部分浏览器 onend 不触发，泵不能被永久卡住。
 *  Per-sentence watchdog (ms): some browsers never fire onend; the pump must not hang. */
const SENTENCE_TIMEOUT_MS = 20000

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

/** 已播出口的字符数（本轮队列累计；barge-in 的「只保留已播文本」原则的计数基础，
 *  当前不消费 —— 本项目上下文源自文本块而非 TTS，中断不产生上下文污染）。
 *  Characters actually spoken (accumulated this round; the counting basis for the
 *  barge-in "only spoken text counts" principle — not consumed yet: context here
 *  comes from text blocks, not TTS, so an interrupt pollutes nothing). */
export const spokenChars = ref(0)

/** 播报代际：新回合/stopSpeak 时 ++，旧回合一切迟到回调据此作废。
 *  Playback generation: bumped on every new round / stopSpeak; every late callback
 *  from an older round invalidates itself against it. */
let speakGen = 0

/** 当前句队列与游标（speakText 重置；pump 逐句推进）。Current sentence queue & cursor. */
let speakQueue: string[] = []
let queueIdx = 0

/** 当前句的收尾回调：stopSpeak/新回合需主动释放，否则 pause() 不触发 onend、泵会悬住。
 *  Current sentence's finish callback: stopSpeak / a new round must release it
 *  actively, otherwise pause() never fires onend and the pump hangs. */
let currentDone: (() => void) | null = null

/** 活跃泵的代际（防同代重复启动；旧代泵退出时不得清掉新代的标记）。
 *  Generation of the active pump (prevents duplicate starts of the same round; an
 *  older pump exiting must not clear a newer pump's marker). */
let activePumpGen = -1

/** API 引擎预取缓存：index → Blob Promise（乱序完成、按序消费）。Prefetch cache. */
let prefetched = new Map<number, Promise<Blob | null>>()

/** 当前 API 播放句柄（修「新 Audio 不停旧 Audio」的叠播 bug）。Current API playback handle. */
let currentAudio: { el: HTMLAudioElement; url: string } | null = null

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

/** 停止一切播报（清队、取消合成、停掉 API Audio、作废迟到回调）。
 *  打断白名单（docs/designs/02 §3.1）：UI 停止 / 新回合 / barge-in 均走这里；
 *  beep 提示音独立于 TTS 管线，不受影响。
 *
 *  Stop all playback (clear queue, cancel synthesis, stop the API audio, void late
 *  callbacks). The interrupt whitelist (docs/designs/02 §3.1): UI stop / new round
 *  / barge-in all route here; the beep chime is outside the TTS pipeline and
 *  unaffected.
 *  @param reason - 打断来源（审计/日志口径）。Interrupt source (audit/log taxonomy). */
export function stopSpeak(reason: 'ui' | 'new_turn' | 'barge_in' = 'ui') {
  speakGen++
  speakQueue = []
  queueIdx = 0
  prefetched.clear()
  try { window.speechSynthesis?.cancel() } catch { /* ignore */ }
  // 先停 Audio 再释放收尾回调：finish 里的 revoke/清理以 currentAudio 为准。
  // Stop the audio before releasing the finish callback; revoke/cleanup inside
  // finish keys off currentAudio.
  const handle = currentAudio
  currentAudio = null
  if (handle) {
    try { handle.el.pause(); handle.el.src = '' } catch { /* ignore */ }
    try { URL.revokeObjectURL(handle.url) } catch { /* ignore */ }
  }
  const done = currentDone
  currentDone = null
  done?.()
  speaking.value = false
  if (reason === 'barge_in') console.log('[TTS] 播报被用户开口打断（barge_in）')
}

/** 释放当前句收尾（新回合复用；不改 speaking —— 由新泵接管）。
 *  Release the current sentence (reused by a new round; does not touch speaking —
 *  the new pump owns it). */
function resetPlayback() {
  speakGen++
  speakQueue = []
  queueIdx = 0
  prefetched.clear()
  try { window.speechSynthesis?.cancel() } catch { /* ignore */ }
  const handle = currentAudio
  currentAudio = null
  if (handle) {
    try { handle.el.pause(); handle.el.src = '' } catch { /* ignore */ }
    try { URL.revokeObjectURL(handle.url) } catch { /* ignore */ }
  }
  const done = currentDone
  currentDone = null
  done?.()
}

/** 播放单句（浏览器引擎）。Play one sentence (browser engine).
 *  同步完成路径：最后一步的 finish 里直接按代际复位 speaking（保证 onend 触发即复位，
 *  与既有测试契约一致）；泵末尾的复位是兜底。
 *
 *  Synchronous completion path: finish resets speaking by generation right there
 *  (so an onend that fires clears immediately, matching the existing test
 *  contract); the pump's own reset is a backstop.
 *  @param text - 句文本。Sentence text.
 *  @param gen - 本轮代际。Round generation.
 *  @returns 播放结束（含被打断）的 Promise。Promise resolving when done (or interrupted). */
function playBrowser(text: string, gen: number): Promise<void> {
  return new Promise((resolve) => {
    if (typeof window === 'undefined' || !window.speechSynthesis) { resolve(); return }
    let settled = false
    let timer: ReturnType<typeof setTimeout> | null = null
    const finish = () => {
      if (settled) return
      settled = true
      if (currentDone === finish) currentDone = null
      if (timer) clearTimeout(timer)
      // 最后一句完成且仍是本代：同步复位（泵的复位是微任务兜底）。
      if (gen === speakGen && queueIdx >= speakQueue.length) speaking.value = false
      resolve()
    }
    try {
      const u = new SpeechSynthesisUtterance(text.replace(/\n/g, '，'))
      const s = ttsSettings.value
      u.volume = s.volume
      u.rate = s.rate
      u.pitch = s.pitch
      const v = resolveVoice()
      if (v) { u.voice = v; u.lang = v.lang } else { u.lang = 'zh-CN' }
      u.onend = finish
      u.onerror = finish
      currentDone = finish
      timer = setTimeout(finish, SENTENCE_TIMEOUT_MS)
      requestAnimationFrame(() => {
        if (settled) return  // 排队间隙已被打断。Interrupted before dispatch.
        try { window.speechSynthesis.speak(u) } catch { finish() }
      })
    } catch { finish() }
  })
}

/** 取一句的音频（预取命中或现场合成）。Fetch one sentence's audio (prefetch hit or live).
 *  @param text - 句文本。Sentence text.
 *  @param gen - 本轮代际（作废检查）。Round generation (invalidation check).
 *  @returns Blob；失败或已作废返回 null。Blob; null on failure or invalidation. */
async function fetchSentence(text: string, gen: number): Promise<Blob | null> {
  try {
    const res = await fetch('/api/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, voice: ttsSettings.value.apiVoice || undefined }),
    })
    if (!res.ok) throw new Error(`TTS HTTP ${res.status}`)
    const blob = await res.blob()
    return gen === speakGen ? blob : null
  } catch (e) {
    console.warn('[TTS] 句合成失败:', e)
    return null
  }
}

/** 播放单句（API 引擎；失败逐句回退浏览器）。Play one sentence (API engine;
 *  falls back to the browser engine per sentence on failure).
 *  @param text - 句文本。Sentence text.
 *  @param idx - 句在队列中的下标（预取键）。Sentence index in the queue (prefetch key).
 *  @param gen - 本轮代际。Round generation. */
async function playApi(text: string, idx: number, gen: number): Promise<void> {
  const cached = prefetched.get(idx)
  prefetched.delete(idx)
  const blob = cached ? await cached : await fetchSentence(text, gen)
  if (gen !== speakGen) return  // 合成在途被本轮作废。Invalidated mid-synthesis.
  if (!blob) { await playBrowser(text, gen); return }  // 逐句回退。Per-sentence fallback.
  await new Promise<void>((resolve) => {
    let settled = false
    const finish = () => {
      if (settled) return
      settled = true
      if (currentDone === finish) currentDone = null
      const handle = currentAudio
      currentAudio = null
      if (handle) {
        try { URL.revokeObjectURL(handle.url) } catch { /* ignore */ }
      }
      if (gen === speakGen && queueIdx >= speakQueue.length) speaking.value = false
      resolve()
    }
    try {
      const url = URL.createObjectURL(blob)
      const audio = new Audio(url)
      currentAudio = { el: audio, url }
      audio.volume = ttsSettings.value.volume
      audio.onended = finish
      audio.onerror = finish
      currentDone = finish
      audio.play().catch(finish)
    } catch { finish() }
  })
}

/** 为「接下来两句」播种预取（当前句开始播放时调用）。
 *  Seed prefetch for the next two sentences (called when the current one starts). */
function seedPrefetch(gen: number) {
  for (let k = 0; k < PREFETCH_WINDOW; k++) {
    const idx = queueIdx + k
    if (idx < speakQueue.length && !prefetched.has(idx)) {
      prefetched.set(idx, fetchSentence(speakQueue[idx], gen))
    }
  }
}

/** 队列泵：逐句播放直到队列空或被新代接管。Queue pump: plays sentence by
 *  sentence until the queue empties or a newer generation takes over.
 *  @param gen - 本轮代际。Round generation. */
async function runPump(gen: number) {
  const api = ttsSettings.value.engine === 'api'
  speaking.value = true
  while (gen === speakGen && queueIdx < speakQueue.length) {
    const i = queueIdx
    const text = speakQueue[i]
    queueIdx = i + 1
    if (api) seedPrefetch(gen)  // 播本句期间预取后续。Prefetch upcoming while this plays.
    await (api ? playApi(text, i, gen) : playBrowser(text, gen))
    if (gen === speakGen) spokenChars.value += text.length
  }
  if (gen === speakGen) speaking.value = false
}

/** 启动（或接管）队列泵。Start (or take over) the queue pump. */
function pump() {
  const gen = speakGen
  if (gen === activePumpGen) return  // 同代已在跑。Same generation already pumping.
  activePumpGen = gen
  void runPump(gen).finally(() => {
    if (activePumpGen === gen) activePumpGen = -1
  })
}

/** 按当前引擎播报（整段入队、切句逐播；新播报总是替换旧播报）。
 *  Broadcast by current engine (the whole text is queued and played sentence by
 *  sentence; a new broadcast always replaces the previous one).
 *  @param text - 要播报的文本。Text to broadcast. */
export function speakText(text: string) {
  if (!text || typeof window === 'undefined') return
  const sentences = splitSentences(text)
  if (!sentences.length) return
  resetPlayback()
  speakQueue = sentences
  queueIdx = 0
  spokenChars.value = 0
  pump()
}

/** 自动播报入口：总开关为关时不发声（区别于「试听」的强制播放）。
 *  Auto broadcast entry: no sound when master switch is off (different from "preview" forced playback).
 *  @param text - 要播报的文本。Text to broadcast. */
export function speakAuto(text: string) {
  if (ttsSettings.value.speakEnabled) speakText(text)
}

/** 试听当前设置。Preview current settings. */
export function testVoice() {
  speakText('你好，我是衍衡。这样调整的音量和声音可以吗？')
}

/** TTS 管理 composable。TTS management composable.
 *  @returns 包含 TTS 设置、保存、语音列表、播报等方法的接口。Interface containing TTS settings, save, voice list, broadcast methods etc. */
export function useTts() {
  return {
    ttsSettings, speaking, spokenChars, saveTts, getVoices, loadVoices,
    speakText, testVoice, speakAuto, toggleSpeak, stopSpeak,
  }
}
