/**
 * 块注册协议 — 新块类型即插即用，页面零改动
 *
 * 每种块类型注册一个渲染规格（组件 + 摘要器 + 播报器）；未注册的类型与
 * ext:* 扩展块统一走 UnknownBlock 兜底（保留原始 JSON，不丢数据）。
 *
 * Block registry protocol — new block types plug in with zero page changes.
 * Each type registers a render spec (component + summarizer + speaker);
 * unregistered types and ext:* extensions fall back to UnknownBlock (raw JSON
 * preserved, never dropped).
 */
import type { Component } from 'vue'
import type { Block, Skin } from './types'

/** 块渲染规格。Block renderer spec. */
export interface BlockRendererSpec {
  /** 渲染组件（props: { block, skin }）。Render component (props: { block, skin }). */
  component: Component
  /** 摘要皮肤的一行摘要（MiniHistory / 汇总卡折叠态用）；返回空串表示不摘要。
   *  One-line summary for the summary skin; empty string means skip. */
  summarize?: (b: Block) => string
  /** 块级语音贡献（speechForBlocks 用）；null 表示不播。Block-level speech contribution; null = silent. */
  speak?: (b: Block) => string | null
}

const registry = new Map<string, BlockRendererSpec>()

/** 未注册类型的兜底规格（由 index.ts 注入 UnknownBlock，避免循环依赖）。
 *  Fallback spec for unregistered types (injected by index.ts to avoid cycles). */
let fallback: BlockRendererSpec | null = null

/**
 * 注册块类型的渲染规格（同类型重复注册以最后一次为准）。
 * Register a render spec for a block type (last registration wins).
 *
 * @param type - 块类型（ext:<name> 形式注册扩展块）。Block type (ext:<name> for extensions).
 * @param spec - 渲染规格。Render spec.
 */
export function registerBlock(type: string, spec: BlockRendererSpec) {
  registry.set(type, spec)
}

/**
 * 设置未注册类型的兜底规格。Set the fallback spec for unregistered types.
 *
 * @param spec - 兜底规格。Fallback spec.
 */
export function setFallbackBlock(spec: BlockRendererSpec) {
  fallback = spec
}

/**
 * 取块类型的渲染规格；未注册 → 兜底规格。Get the spec for a block type; unregistered falls back.
 *
 * @param type - 块类型。Block type.
 * @returns 渲染规格。The render spec.
 */
export function getBlockSpec(type: string): BlockRendererSpec {
  return registry.get(type) ?? fallback ?? {
    component: { template: '<div class="blk-unknown">{{ block.type }}</div>' },
  }
}

/**
 * 块的一行摘要（摘要皮肤用）；未注册类型退化为类型名。
 * One-line summary of a block (summary skin); unregistered types degrade to the type name.
 *
 * @param b - 消息块。The message block.
 * @returns 摘要文本。The summary text.
 */
export function summarizeBlock(b: Block): string {
  const spec = registry.get(b.type)
  return spec?.summarize?.(b) ?? `[${b.type}]`
}

/**
 * 块的语音贡献（speechForBlocks 用）；未注册类型默认不播。
 * Speech contribution of a block (for speechForBlocks); unregistered types are silent.
 *
 * @param b - 消息块。The message block.
 * @returns 播报文本或 null。Speech text or null.
 */
export function speakBlock(b: Block): string | null {
  const spec = registry.get(b.type)
  return spec?.speak?.(b) ?? null
}

/** 注册表是否已有该类型（测试/调试用）。Whether the type is registered (tests/debug). */
export function hasBlock(type: string): boolean {
  return registry.has(type)
}
