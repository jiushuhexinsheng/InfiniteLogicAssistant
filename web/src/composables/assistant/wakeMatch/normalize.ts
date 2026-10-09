// 拆分自 wakeMatch.ts（重构：纯移动，无行为变化）。Split from wakeMatch.ts (pure move).
// ── 归一化 ──

/** 需要剥掉的标点和空白字符。Punctuation and whitespace to strip. */
const STRIP_CHARS = new Set(
  ' \t\n\r\v\f' +
  '!\"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~' +
  '，。！？、；：\u201c\u201d\u2018\u2019（）《》【】〈〉「」『』…—～·'
)

/** 归一化：去空白与中英文标点。Normalize: strip whitespace and punctuation. */
export function normalize(text: string): string {
  let out = ''
  for (const ch of text) {
    if (!STRIP_CHARS.has(ch)) out += ch
  }
  return out
}
