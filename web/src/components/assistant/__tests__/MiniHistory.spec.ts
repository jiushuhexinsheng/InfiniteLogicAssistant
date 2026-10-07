// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import MiniHistory from '../MiniHistory.vue'
import { wakeEnabled } from '../../../composables/assistant/store'
import type { StateVisual } from '../../../composables/useAssistantVisuals'

const VISUAL: StateVisual = { icon: 'ear', label: '', color: '#fff', fx: 'fx-idle', grad: 'brand' }

/**
 * 空态文案：简化为统一提示（不再按状态区分，状态信息由悬浮球/状态胶囊承载）。
 * Empty-state copy: simplified to one generic hint (state detail lives on the ball / status pill).
 *
 * 唤醒开关感知（2026-10-07 遗留审计）：唤醒未开启时空态仍叫「说唤醒词」——说了没人听。
 * Wake-switch awareness (2026-10-07 leftover audit): with wake off the empty state still
 * said "say the wake word" — advice nothing was listening for.
 */
afterEach(() => {
  wakeEnabled.value = false
})

describe('MiniHistory 空态文案', () => {
  const base = { messages: [], visual: VISUAL, wakeHint: '「衍衡」或「洛吉斯」' }

  /** 空态显示统一提示和唤醒词（唤醒开时）。Empty state shows the prompt and wake keywords when wake is on. */
  it('空态显示「开始对话」和唤醒词', () => {
    wakeEnabled.value = true
    const w = mount(MiniHistory, { props: { ...base, state: 'idle' as any } })
    expect(w.text()).toContain('开始对话')
    expect(w.text()).toContain('「衍衡」或「洛吉斯」')
  })

  /** 唤醒关闭：不叫喊唤醒词，给出文字/双击通话出路。Wake off: no shout-the-wake-word advice; text/double-click instead. */
  it('唤醒关闭时空态不再叫人喊唤醒词', () => {
    wakeEnabled.value = false
    const w = mount(MiniHistory, { props: { ...base, state: 'idle' as any } })
    expect(w.text()).not.toContain('唤醒')
    expect(w.text()).toContain('双击悬浮球开通话')
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
