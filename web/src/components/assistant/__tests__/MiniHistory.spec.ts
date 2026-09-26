// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import MiniHistory from '../MiniHistory.vue'
import type { StateVisual } from '../../../composables/useAssistantVisuals'

const VISUAL: StateVisual = { icon: 'ear', label: '', color: '#fff', fx: 'fx-idle', grad: 'brand' }

/**
 * 空态文案：简化为统一提示（不再按状态区分，状态信息由悬浮球/状态胶囊承载）。
 * Empty-state copy: simplified to one generic hint (state detail lives on the ball / status pill).
 */
describe('MiniHistory 空态文案', () => {
  const base = { messages: [], visual: VISUAL, wakeHint: '「衍衡」或「洛吉斯」' }

  /** 空态显示统一提示和唤醒词。Empty state shows the generic prompt and wake keywords. */
  it('空态显示「开始对话」和唤醒词', () => {
    const w = mount(MiniHistory, { props: { ...base, state: 'idle' as any } })
    expect(w.text()).toContain('开始对话')
    expect(w.text()).toContain('「衍衡」或「洛吉斯」')
  })

  /** 不同状态下空态文案一致（简化）。The empty copy is identical across states (simplified). */
  it('不同状态文案一致', () => {
    const states = ['idle', 'listening', 'standby', 'recording', 'awaiting_answer'] as const
    for (const s of states) {
      const w = mount(MiniHistory, { props: { ...base, state: s as any } })
      expect(w.text()).toContain('开始对话')
    }
  })
})
