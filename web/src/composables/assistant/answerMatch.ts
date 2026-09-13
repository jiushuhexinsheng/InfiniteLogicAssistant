import type { QuestionOption } from '../../types'

/**
 * 把语音转写文本匹配到某个选项。
 *
 * **只做 trim 后精确相等** —— 不做子串、模糊、大小写归一、全角半角转换或标点剥离。
 * 任何归一化都是模糊匹配的入口，而这条路径参与「是否批准执行」的判定，必须保守：
 * 不命中就返回 null，调用方按普通文本处理。
 *
 * Match a speech transcript against a question option.
 *
 * **Trim-then-exact-equality only** — no substring, fuzzy, case, width or punctuation
 * normalisation. Any normalisation is a gateway to fuzzy matching, and this path takes
 * part in deciding whether an action is approved, so it must stay conservative: a miss
 * returns null and the caller treats the text as plain input.
 *
 * @param text 转写文本。The transcript.
 * @param options 待匹配的选项列表。The options to match against.
 * @returns 命中的选项，未命中为 null。The matched option, or null.
 */
export function matchOption(text: string, options: QuestionOption[]): QuestionOption | null {
  const t = text.trim()
  if (!t) return null
  for (const opt of options) {
    if (t === opt.label.trim()) return opt
  }
  return null
}
