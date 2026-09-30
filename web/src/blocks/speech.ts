/**
 * 语音播报管线 — 块级播报策略 → 回合播报统一出口
 *
 * 修复「markdown 记号被念出来」：text 块播报前剥离记号；
 * thinking 默认不播；回合收尾优先 summary.tts_text（汇总卡为权威出口）。
 *
 * Speech pipeline — per-block speech policy → unified turn speech exit.
 * Fixes "markdown tokens get read aloud": text blocks are stripped first;
 * thinking is silent by default; turn endings prefer summary.tts_text (the
 * summary card is the authoritative exit).
 */
import type { Block } from './types'
import { speakBlock } from './registry'

/**
 * 剥离 markdown 记号为可朗读文本（代码围栏降级为「代码块」提示）。
 * Strip markdown tokens into speakable text (code fences degrade to a "code block" hint).
 *
 * @param md - markdown 文本。Markdown text.
 * @returns 可朗读文本。Speakable text.
 */
export function stripMarkdown(md: string): string {
  if (!md) return ''
  let s = md
  // 代码围栏 → 提示（不念代码本体）
  s = s.replace(/```[^\n]*\n([\s\S]*?)```/g, '，代码块，')
  s = s.replace(/`([^`\n]+)`/g, '$1')
  // 图片 → alt 文本
  s = s.replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
  // 链接 → 只念文字
  s = s.replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
  // 强调记号
  s = s.replace(/(\*\*|__)(.*?)\1/g, '$2')
  s = s.replace(/(\*|_)(.*?)\1/g, '$2')
  // 标题记号
  s = s.replace(/^#{1,6}\s+/gm, '')
  // 列表记号
  s = s.replace(/^\s*[-*+]\s+/gm, '')
  s = s.replace(/^\s*\d+\.\s+/gm, '')
  // 引用
  s = s.replace(/^\s*>\s+/gm, '')
  // 水平线
  s = s.replace(/^[-=*]{3,}\s*$/gm, '')
  // 折叠多余空白（保留句子间的换行 → 空格）
  s = s.replace(/\s+/g, ' ').trim()
  return s
}

/**
 * 一个回合的块列表 → 播报文本（统一出口）。
 *
 * 优先 summary 块的 tts_text（每回合一次、内容可预期）；没有 summary 时按块级
 * 策略拼接（thinking/tool/code/image/file/answer/unknown 默认不播）。
 *
 * Turn blocks → speech text (unified exit). Prefers the summary block's
 * tts_text (once per turn, predictable); without one, joins per-block speech
 * contributions (thinking/tool/code/image/file/answer/unknown silent by default).
 *
 * @param blocks - 本回合的块列表。The turn's block list.
 * @returns 播报文本（空串表示不播）。Speech text (empty = silent).
 */
export function speechForBlocks(blocks: Block[]): string {
  // 权威出口：回合汇总卡
  const summary = [...blocks].reverse().find(b => b.type === 'summary')
  if (summary?.payload?.tts_text) return String(summary.payload.tts_text)
  if (summary?.payload?.summary_text) return String(summary.payload.summary_text)

  const parts: string[] = []
  for (const b of blocks) {
    // meta.tts 显式 skip 直接跳过（块级播报策略）
    if (b.meta?.tts === 'skip') continue
    const s = speakBlock(b)
    if (s && s.trim()) parts.push(s.trim())
  }
  return parts.join('，')
}

/** 单句长度上限：超长句按逗号二分（句级播放的粒度控制）。
 *  Max sentence length: longer sentences are halved on commas (granularity control
 *  for sentence-level playback). */
const MAX_SENTENCE = 120

/** 尾句短于此长度时并入前句（避免孤字尾音）。Merge a trailing fragment shorter
 *  than this into the previous sentence (avoids a stray-syllable tail). */
const MIN_TAIL = 8

/**
 * 把文本切为可逐句播报的句子（句级流式 TTS 的入队粒度）。
 *
 * 规则：按 。！？；; 换行 断句，句末的右引号/括号归入本句；超长句按逗号二分；
 * 尾句过短并入前句；空句丢弃。输入假定已经过 stripMarkdown（useTts 统一入口对
 * 任意文本调用，未 strip 的直接文本同样可切）。
 *
 * Split text into sentences for sentence-level playback (the enqueue granularity of
 * sentence-streaming TTS). Rules: split on 。！？；; and newlines, keeping a trailing
 * closing quote/bracket with its sentence; halve overlong sentences on commas;
 * merge an overly short tail; drop empties. Input is assumed to have gone through
 * stripMarkdown already (useTts applies this to any text; raw text splits fine too).
 *
 * @param text - 待切文本。Text to split.
 * @returns 句子列表（可为空）。List of sentences (may be empty).
 */
export function splitSentences(text: string): string[] {
  if (!text) return []
  const src = text.replace(/\r/g, '')
  const CLOSE = '"\'”’』」）)》】'
  const DELIM = '。！？；;\n'

  // 一档：终结符断句，后随右引号/括号归入本句。
  const rough: string[] = []
  let buf = ''
  for (let i = 0; i < src.length; i++) {
    buf += src[i]
    if (DELIM.includes(src[i])) {
      while (i + 1 < src.length && CLOSE.includes(src[i + 1])) buf += src[++i]
      if (buf.trim()) rough.push(buf.trim())
      buf = ''
    }
  }
  if (buf.trim()) rough.push(buf.trim())

  // 二档：超长句按逗号二分（回退硬切防死循环）。
  const split: string[] = []
  for (const s of rough) {
    if (s.length <= MAX_SENTENCE) { split.push(s); continue }
    let rest = s
    while (rest.length > MAX_SENTENCE) {
      let cut = -1
      for (let i = 100; i < Math.min(MAX_SENTENCE, rest.length); i++) {
        if (',，、'.includes(rest[i])) cut = i + 1
      }
      if (cut < 0) cut = MAX_SENTENCE
      split.push(rest.slice(0, cut))
      rest = rest.slice(cut)
    }
    if (rest) split.push(rest)
  }

  // 三档：尾句过短并入前句。
  for (let i = split.length - 1; i > 0; i--) {
    if (split[i].length < MIN_TAIL) {
      split[i - 1] += split[i]
      split.splice(i, 1)
    }
  }
  return split.filter(s => s.trim())
}
