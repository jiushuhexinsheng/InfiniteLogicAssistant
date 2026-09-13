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
  const base = { messages: [], visual: VISUAL, wakeHint: '「衍衡」或「洛吉斯」' }

  /** 待答态：提示可直接开口。Awaiting an answer: prompt the user to just speak. */
  it('awaiting_answer 提示可直接开口作答', () => {
    const w = mount(MiniHistory, { props: { ...base, state: 'awaiting_answer' as any } })
    expect(w.text()).toContain('回答')
  })

  /** 待机态：提示处于待机并要唤醒词继续。
   *
   *  两个断言缺一不可：只断言唤醒词会假通过（**兜底文案本就含唤醒词** —— 组件在无
   *  `wakeHint` 时有内置默认值），只断言「待机」则测不到「要用户说什么」。
   *
   *  Both assertions are needed. Asserting only the wake word would pass for the wrong reason —
   *  the fallback copy already contains it, since the component ships a built-in default hint —
   *  while asserting only "standby" would not prove it tells the user what to say. */
  it('standby 提示待机并要唤醒词继续', () => {
    const w = mount(MiniHistory, { props: { ...base, state: 'standby' as any } })
    expect(w.text()).toContain('待机')
    expect(w.text()).toContain('「衍衡」或「洛吉斯」')
  })

  /** 原有 listening 文案不变（回归）。The existing listening copy is unchanged (regression). */
  it('原有 listening 文案不变', () => {
    const w = mount(MiniHistory, { props: { ...base, state: 'listening' as any } })
    expect(w.text()).toContain('聆听中')
  })
})
