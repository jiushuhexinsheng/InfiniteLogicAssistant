// 拆分自 wakeMatch.ts（重构：纯移动，无行为变化）。Split from wakeMatch.ts (pure move).
import { PINYIN_TABLE } from './pinyinTable'

/** 构建 反向索引：汉字 → 无声调拼音。Build reverse index: character → toneless pinyin. */
const CHAR_TO_PINYIN = new Map<string, string>()
for (const [py, chars] of Object.entries(PINYIN_TABLE)) {
  for (const ch of chars) {
    if (!CHAR_TO_PINYIN.has(ch)) CHAR_TO_PINYIN.set(ch, py)
  }
}

/**
 * 把文本转成无声调拼音串，并建立拼音下标 → 原字符下标的映射。
 * Convert text to a toneless pinyin string with a pinyin-index → char-index map.
 *
 * 未知字符保留原样（ASCII / 数字 / 标点走兜底，各占 1 个拼音位）。
 * Unknown characters are kept as-is (fallback for ASCII / digits / punctuation, each occupies 1 pinyin slot).
 */
export function toPinyinMapped(text: string): { py: string; map: number[] } {
  let py = ''
  const map: number[] = [] // map[i] = 第 i 个拼音字符对应 text 中的第几个字符
  for (let ci = 0; ci < text.length; ci++) {
    const chPy = CHAR_TO_PINYIN.get(text[ci]) ?? text[ci]
    for (let k = 0; k < chPy.length; k++) {
      py += chPy[k]
      map.push(ci)
    }
  }
  return { py, map }
}

/** 把文本转成无声调拼音串。Convert text to a toneless pinyin string. */
export function toPinyin(text: string): string {
  return toPinyinMapped(text).py
}

/**
 * 把文本转成**逐字符对齐**的拼音 token 列表（每个字符一个 token）。
 *
 * 与后端 `core/voice/pinyin.py::to_syllables` 同语义：中文取无声调拼音，
 * 非中文（ASCII/数字/未知字）保留原字符、各占一个 token。唤醒判定必须按
 * token 序列比较，不能把拼音拼成扁平字符串后 `indexOf` —— 否则会跨音节
 * 误命中（如 "tian" 中的 "an"）。
 *
 * Convert text to a **per-character aligned** pinyin token list (one token per
 * character). Same semantics as backend `to_syllables`: Chinese → toneless pinyin,
 * non-Chinese (ASCII/digits/unknown) → the character itself, one token each. Wake
 * matching must compare token sequences; a flat `indexOf` can match across syllable
 * boundaries (e.g. "an" inside "tian").
 */
export function toPinyinTokens(text: string): string[] {
  return Array.from(text).map((ch) => CHAR_TO_PINYIN.get(ch) ?? ch)
}
