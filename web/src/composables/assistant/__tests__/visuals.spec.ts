import { afterEach, describe, expect, it } from 'vitest'
import { STATE_VISUALS, resolveStateLabel } from '../../useAssistantVisuals'
import { callActive } from '../store'

/**
 * 通话态状态文案（spec 2026-10-05-call-mode-funnel R2：「状态胶囊文案改……
 * `useAssistantVisuals.ts` 映射表同步改」）。
 *
 * 回归背景（2026-10-07 遗留审计）：实施时特判只写进了 StatusPill 组件，
 * 映射表本身没改 —— 导航胶囊、StartPage 徽章、ConsoleStatus 等共享 stateLabel
 * 的表面在通话中仍显示「聆听中…说「衍衡」」（免唤醒通话里叫人喊唤醒词）。
 * 修复必须落在映射表层，一处改、全表面生效。
 *
 * Call-state copy (spec R2: the mapping table is the authorized edit site).
 * Regression context (2026-10-07 leftover audit): the original implementation put the
 * special case inside StatusPill only, so every surface that shares stateLabel (nav pill,
 * StartPage badge, ConsoleStatus) still said "聆听中…说「衍衡」" during a wake-free call.
 * The fix belongs in the mapping table: edit once, every surface follows.
 */
afterEach(() => {
  callActive.value = false
})

describe('通话态状态文案（映射表层，全表面共享）', () => {
  it('通话中聆听态 →「通话聆听中」，不再喊唤醒词', () => {
    callActive.value = true
    expect(resolveStateLabel(STATE_VISUALS.listening, '「衍衡」')).toBe('通话聆听中')
  })

  // standby（待机态）文案已随「取消限时回答」整套删除 —— 回答永不限时，不再有待机。

  it('通话中续聊态 → 不再喊唤醒词', () => {
    callActive.value = true
    const s = resolveStateLabel(STATE_VISUALS.followup, '「衍衡」')
    expect(s).not.toContain('「')
  })

  it('非通话态两条文案保持原样（守护）', () => {
    expect(resolveStateLabel(STATE_VISUALS.listening, '「衍衡」')).toBe('聆听中…说「衍衡」')
    expect(resolveStateLabel(STATE_VISUALS.followup, '「衍衡」')).toBe('可直接开口，或说「衍衡」')
  })
})
