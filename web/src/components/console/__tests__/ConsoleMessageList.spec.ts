// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ConsoleMessageList from '../ConsoleMessageList.vue'
import { wakeEnabled } from '../../../composables/assistant/store'

/**
 * 控制台欢迎横幅的状态段随唤醒开关走（2026-10-07 遗留审计）：唤醒未开启时横幅仍写
 * 「在线 · 说「衍衡」唤醒」——提示与行为不一致。
 *
 * The console welcome banner's status segment follows the wake switch (2026-10-07 leftover
 * audit): with wake off it still read "在线 · 说「衍衡」唤醒" — copy that contradicts behavior.
 */
afterEach(() => {
  wakeEnabled.value = false
})

describe('ConsoleMessageList 欢迎横幅', () => {
  it('唤醒开 → 「在线 · 说…唤醒」（守护）', () => {
    wakeEnabled.value = true
    const w = mount(ConsoleMessageList, { props: { messages: [] } })
    expect(w.find('.w-state').text()).toContain('说')
    expect(w.find('.w-state').text()).toContain('唤醒')
  })

  it('唤醒关 → 不叫喊唤醒词', () => {
    wakeEnabled.value = false
    const w = mount(ConsoleMessageList, { props: { messages: [] } })
    expect(w.find('.w-state').text()).not.toContain('说')
    expect(w.find('.w-state').text()).toContain('语音唤醒已关')
  })
})
