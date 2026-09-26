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
