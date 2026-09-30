/**
 * 块注册表装配 — 内置块类型的组件 / 摘要器 / 播报器一次性注册
 *
 * 新块类型 = 此处 registerBlock 一行 + 一个组件，页面零改动。
 * 扩展块（ext:<name>）同样注册即可渲染。
 *
 * Block registry assembly — one-shot registration of component / summarizer /
 * speaker for built-in block types. A new block type = one registerBlock line
 * plus a component; pages change nothing. Extension blocks (ext:<name>) render
 * the same way once registered.
 */
import { registerBlock, setFallbackBlock, summarizeBlock, speakBlock, getBlockSpec, hasBlock } from './registry'
import { stripMarkdown, speechForBlocks } from './speech'
import { applyEvent, finalizeBlocks, makeBlock, newBlockId } from './normalize'
import ThinkingBlock from '../components/blocks/ThinkingBlock.vue'
import ToolBlock from '../components/blocks/ToolBlock.vue'
import TextBlock from '../components/blocks/TextBlock.vue'
import CodeBlock from '../components/blocks/CodeBlock.vue'
import ImageBlock from '../components/blocks/ImageBlock.vue'
import FileBlock from '../components/blocks/FileBlock.vue'
import QuestionBlock from '../components/blocks/QuestionBlock.vue'
import AnswerBlock from '../components/blocks/AnswerBlock.vue'
import NoticeBlock from '../components/blocks/NoticeBlock.vue'
import TurnSummaryBlock from '../components/blocks/TurnSummaryBlock.vue'
import SourcesBlock from '../components/blocks/SourcesBlock.vue'
import UnknownBlock from '../components/blocks/UnknownBlock.vue'
import type { Block } from './types'

/** 截 80 字摘要（摘要皮肤沿用 MiniHistory 的截断口径）。
 *  Truncate to 80 chars (summary skin keeps MiniHistory's truncation rule). */
function clip(s: string, n = 80): string {
  const t = (s || '').replace(/\s+/g, ' ').trim()
  return t.length > n ? t.slice(0, n) + '…' : t
}

// ─── 思考模块：默认折叠不播 ───
registerBlock('thinking', {
  component: ThinkingBlock,
  summarize: () => '',  // 摘要皮肤不显示思考
  speak: () => null,    // 默认不播报（meta.tts=summary 时由策略层播 payload.summary）
})

// ─── 工具调用模块 ───
registerBlock('tool', {
  component: ToolBlock,
  summarize: (b) => `🔧 ${b.payload.name}`,
  speak: () => null,
})

// ─── 正文模块（代码/文档/图片在 text 内由 variant 与围栏区分；独立 code/image 同注册）───
registerBlock('text', {
  component: TextBlock,
  summarize: (b) => clip(stripMarkdown(String(b.payload.md || ''))),
  speak: (b) => {
    const s = stripMarkdown(String(b.payload.md || ''))
    return s || null
  },
})

registerBlock('code', {
  component: CodeBlock,
  summarize: (b) => `code(${b.payload.language || 'text'})`,
  speak: (b) => {
    const lines = String(b.payload.code || '').split('\n').length
    return `代码块，共 ${lines} 行`
  },
})

registerBlock('image', {
  component: ImageBlock,
  summarize: (b) => `🖼 ${b.payload.alt || '图片'}`,
  speak: (b) => (b.payload.alt ? `图片：${b.payload.alt}` : '图片'),
})

registerBlock('file', {
  component: FileBlock,
  summarize: (b) => `📄 ${b.payload.name || '文件'}`,
  speak: () => null,
})

// ─── 系统-操作员对话模块 ───
registerBlock('question', {
  component: QuestionBlock,
  summarize: (b) => `❓ ${clip(String(b.payload.question || ''))}`,
  // 问句在到达时已即时播报（useChat onQuestion）—— 回合收尾不得重播，
  // 否则同一个问题会响两遍。
  // The question is already spoken the moment it arrives (useChat onQuestion) —
  // the turn's closing speech must not repeat it.
  speak: () => null,
})

registerBlock('answer', {
  component: AnswerBlock,
  summarize: (b) => `💬 ${clip(String(b.payload.text || b.payload.choice || ''))}`,
  speak: () => null,
})

// ─── 系统提示 ───
registerBlock('notice', {
  component: NoticeBlock,
  summarize: (b) => clip(String(b.payload.text || '')),
  speak: (b) => {
    const t = String(b.payload.text || '')
    return t || null
  },
})

// ─── 汇总模块：回合汇总卡（语音播报统一出口）───
registerBlock('summary', {
  component: TurnSummaryBlock,
  summarize: (b) => clip(String(b.payload.summary_text || '已完成')),
  speak: (b) => String(b.payload.tts_text || b.payload.summary_text || '') || null,
})

// ─── RAG 来源模块（docs/designs/05）：编号 chips，不进摘要皮肤、不播报 ───
registerBlock('sources', {
  component: SourcesBlock,
  summarize: (b) => `📄 ${Array.isArray(b.payload.items) ? b.payload.items.length : 0} 个来源`,
  speak: () => null,
})

// ─── 未知/扩展块兜底 ───
setFallbackBlock({
  component: UnknownBlock,
  summarize: (b) => `[${b.type}]`,
  speak: () => null,
})
registerBlock('unknown', {
  component: UnknownBlock,
  summarize: (b) => `[${b.type}]`,
  speak: () => null,
})

export {
  registerBlock, setFallbackBlock, summarizeBlock, speakBlock, getBlockSpec, hasBlock,
  stripMarkdown, speechForBlocks,
  applyEvent, finalizeBlocks, makeBlock, newBlockId,
}
export type { Block }
