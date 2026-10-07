// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import NavSystemInfo from '../NavSystemInfo.vue'
import { callActive, state } from '../../../composables/assistant/store'

/**
 * 导航胶囊是通话态文案的最显眼表面（顶栏常驻）。2026-10-07 遗留审计的用户主诉
 * 「页面提示还是喊唤醒词」即此处：通话中它显示「聆听中…说「衍衡」或「洛吉斯」」，
 * 因为通话特判只写在 StatusPill 组件、没落进共享映射表。
 *
 * The nav pill is the most visible surface for call-state copy (always in the header).
 * The 2026-10-07 leftover report ("the page still tells me to shout the wake word") is this
 * exact pill: during a call it showed "聆听中…说「衍衡」或「洛吉斯」" because the call
 * special case lived only in StatusPill and never reached the shared mapping table.
 */
afterEach(() => {
  callActive.value = false
  state.value = 'idle'
})

describe('NavSystemInfo 通话态文案', () => {
  it('通话中聆听态 → 胶囊显示「通话聆听中」', () => {
    state.value = 'listening'
    callActive.value = true
    const w = mount(NavSystemInfo)
    expect(w.text()).toContain('通话聆听中')
    expect(w.text()).not.toContain('说')
  })

  it('非通话态 → 保持「聆听中…说…」（守护）', () => {
    state.value = 'listening'
    const w = mount(NavSystemInfo)
    expect(w.text()).toContain('聆听中…说')
  })
})
