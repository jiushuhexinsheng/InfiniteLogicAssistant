// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import MiniHistory from '../MiniHistory.vue'
import type { StateVisual } from '../../../composables/useAssistantVisuals'

const VISUAL: StateVisual = { icon: 'ear', label: '', color: '#fff', fx: 'fx-idle', grad: 'brand' }

/**
 * 新状态在迷你历史里要有明确文案（否则用户不知道系统在等什么）。
 * The new states need explicit copy in the mini history, or the user cannot tell what the
 * system is waiting for.
 */
describe('MiniHistory 新状态文案', () => {
  const base = { messages: [], visual: VISUAL, wakeKeyword: '小逻小逻' }

  /** 待答态：提示可直接开口。Awaiting an answer: prompt the user to just speak. */
  it('awaiting_answer 提示可直接开口作答', () => {
    const w = mount(MiniHistory, { props: { ...base, state: 'awaiting_answer' as any } })
    expect(w.text()).toContain('回答')
  })

  /** 待机态：提示处于待机并要唤醒词继续。
   *  断言「待机」而非仅「小逻小逻」—— 兜底文案本就含唤醒词，只断言唤醒词会假通过。 */
  it('standby 提示待机并要唤醒词继续', () => {
    const w = mount(MiniHistory, { props: { ...base, state: 'standby' as any } })
    expect(w.text()).toContain('待机')
    expect(w.text()).toContain('小逻小逻')
  })

  /** 原有 listening 文案不变（回归）。The existing listening copy is unchanged (regression). */
  it('原有 listening 文案不变', () => {
    const w = mount(MiniHistory, { props: { ...base, state: 'listening' as any } })
    expect(w.text()).toContain('聆听中')
  })
})
