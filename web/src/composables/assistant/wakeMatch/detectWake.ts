// 拆分自 wakeMatch.ts（重构：纯移动，无行为变化）。Split from wakeMatch.ts (pure move).
import { normalize } from './normalize'
import { toPinyin, toPinyinMapped } from './pinyin'

// ── 唤醒判定 ──

/** 唤醒判定结果。Wake detection result. */
export interface WakeMatch {
  /** 是否命中唤醒词。Whether a wake word hit. */
  matched: boolean
  /** 唤醒词之后的指令（仅唤醒词时为空）。Command after the wake word (empty for bare wake). */
  command: string
}

/** 唤醒冷却时间（毫秒）：唤醒后在此时间内忽略再次唤醒，防止麦克风拾取自己回复造成循环。Wake cooldown (ms). */
export const WAKE_COOLDOWN_MS = 3000

/** 冷却截止时间戳：在此之前不再响应唤醒。Cooldown deadline timestamp. */
let cooldownUntil = 0

/** 进入冷却。Enter cooldown. */
export function enterWakeCooldown() {
  cooldownUntil = Date.now() + WAKE_COOLDOWN_MS
}

/** 是否在冷却期内。Whether currently in cooldown. */
export function isWakeCooldown(): boolean {
  return Date.now() < cooldownUntil
}

/**
 * 判断文本是否**靠近句首**包含唤醒词（拼音级），切出其后内容作为指令。
 *
 * 只要发音对就行，不管 ASR 写成什么字：
 *   「衍衡」「燕恒」「演横」「沿哼」「呃衍衡」… 全部命中。
 *   但「你好帮我查衍衡」不会命中（唤醒词离句首太远，防止误触发循环）。
 *
 * Wake word must be NEAR THE START of the text to avoid feedback loops
 * (assistant's own TTS response being picked up and re-triggering).
 */
export function detectWake(text: string, keywords: string[]): WakeMatch {
  if (isWakeCooldown()) return { matched: false, command: '' }
  const norm = normalize(text)
  const { py: normPy, map: pyMap } = toPinyinMapped(norm)
  /** 允许唤醒词前最多有 2 个汉字的噪音（语气词/口头禅）。Allow up to 2 leading noise chars. */
  const MAX_LEAD_CHARS = 2
  let bestPyLen = 0
  let bestEndChar = -1
  for (const keyword of keywords) {
    const kwNorm = normalize(keyword)
    const kwPy = toPinyin(kwNorm)
    if (!kwPy) continue
    // 在全文查找唤醒词拼音
    const idx = normPy.indexOf(kwPy)
    if (idx === -1) continue
    // 检查唤醒词起始字符位置是否在允许的前导范围内
    const startChar = pyMap[idx]
    if (startChar > MAX_LEAD_CHARS) continue
    if (kwPy.length > bestPyLen) {
      bestPyLen = kwPy.length
      bestEndChar = pyMap[idx + kwPy.length - 1] + 1
    }
  }
  if (bestEndChar < 0) return { matched: false, command: '' }
  return { matched: true, command: norm.slice(bestEndChar) }
}
