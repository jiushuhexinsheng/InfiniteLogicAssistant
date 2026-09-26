/**
 * 块宿主的注入上下文 —— 同级块列表（汇总卡本轮回看用）
 * Block host injection context — sibling block list (for the summary card's turn review)
 */
import type { InjectionKey } from 'vue'
import type { Block } from './types'

/** 同级块列表提供者（BlockHost provide；TurnSummaryBlock inject）。
 *  Sibling block supplier (provided by BlockHost, injected by TurnSummaryBlock). */
export const BLOCKS_CONTEXT: InjectionKey<() => Block[]> = Symbol('blocks-context')
