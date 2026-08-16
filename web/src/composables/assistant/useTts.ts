import { ref } from 'vue'

// ─── 语音播报（双引擎）───
// engine='browser'：浏览器 speechSynthesis（本地语音，零配置）
// engine='api'    ：POST /api/tts（后端 OpenAI 兼容 TTS），失败自动回退浏览器
export type TtsEngine = 'browser' | 'api'

export interface TtsSettings {
  engine: TtsEngine
  volume: number    // 0–1
  rate: number      // 0.1–10（仅浏览器引擎）
  pitch: number     // 0–2（仅浏览器引擎）
  voiceName: string // 浏览器语音名（'' = 系统默认）
  apiVoice: string  // API 语音名（'' = 用后端配置的 voice）
}

const STORAGE_KEY = 'xluo.tts'

/** MiMo 预置音色（mimo-v2.5-tts）；API 模式下拉提示，可自定义输入任意名字 */
export const API_VOICE_SUGGESTIONS = ['Chloe', 'Mia', '冰糖', '茉莉', '苏打', '白桦', 'Dean', 'Milo', 'mimo_default']

function clamp(n: number, min: number, max: number) {
  if (!Number.isFinite(n)) return min
  return Math.min(max, Math.max(min, n))
}

function load(): TtsSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const p = JSON.parse(raw)
      return {
        engine: p.engine === 'api' ? 'api' : 'browser',
        volume: clamp(p.volume ?? 1, 0, 1),
        rate: clamp(p.rate ?? 1, 0.1, 10),
        pitch: clamp(p.pitch ?? 1, 0, 2),
        voiceName: typeof p.voiceName === 'string' ? p.voiceName : '',
        apiVoice: typeof p.apiVoice === 'string' ? p.apiVoice : '',
      }
    }
  } catch { /* 解析失败则用默认 */ }
  return { engine: 'browser', volume: 1, rate: 1, pitch: 1, voiceName: '', apiVoice: '' }
}

/** 全局单例设置（全站共享；滑块/下拉直接改它，下次播报即生效） */
export const ttsSettings = ref<TtsSettings>(load())

export function saveTts() {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(ttsSettings.value)) } catch { /* ignore */ }
}

/** 可用浏览器语音（中文优先，其余兜底） */
export function getVoices(): SpeechSynthesisVoice[] {
  if (typeof window === 'undefined' || !window.speechSynthesis) return []
  const all = window.speechSynthesis.getVoices()
  const zh = all.filter(v => /^zh/i.test(v.lang))
  const others = all.filter(v => !/^zh/i.test(v.lang))
  return [...zh, ...others]
}

/** 语音列表异步就绪时回调（部分浏览器需等 voiceschanged 事件） */
export function loadVoices(cb: () => void) {
  if (typeof window === 'undefined' || !window.speechSynthesis) return
  const s = window.speechSynthesis
  s.getVoices()
  s.onvoiceschanged = () => cb()
  cb()
}

function resolveVoice(): SpeechSynthesisVoice | undefined {
  const vs = getVoices()
  if (!vs.length) return undefined
  const name = ttsSettings.value.voiceName
  if (name) return vs.find(v => v.name === name)
  return vs.find(v => /^zh/i.test(v.lang) && v.localService)
    || vs.find(v => /^zh/i.test(v.lang))
    || vs[0]
}

/** 浏览器语音播报 */
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
    requestAnimationFrame(() => {
      try { window.speechSynthesis.speak(u) } catch { /* ignore */ }
    })
  } catch { /* ignore */ }
}

/** API 语音播报（后端 OpenAI 兼容 TTS）；失败自动回退浏览器 */
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
    const fail = () => { URL.revokeObjectURL(url); speakBrowser(text) }
    audio.onended = () => URL.revokeObjectURL(url)
    audio.onerror = fail
    await audio.play().catch(fail)
  } catch (e) {
    console.warn('[TTS] API 播报失败，回退本地语音:', e)
    speakBrowser(text)
  }
}

/** 按当前引擎播报 */
export function speakText(text: string) {
  if (!text || typeof window === 'undefined') return
  if (ttsSettings.value.engine === 'api') {
    void speakApi(text)
  } else {
    speakBrowser(text)
  }
}

/** 试听当前设置 */
export function testVoice() {
  speakText('你好，我是小逻。这样调整的音量和声音可以吗？')
}

export function useTts() {
  return { ttsSettings, saveTts, getVoices, loadVoices, speakText, testVoice }
}
