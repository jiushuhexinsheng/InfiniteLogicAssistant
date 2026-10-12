// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ConsoleMessageList from '../ConsoleMessageList.vue'

/**
 * 对话页去掉身份头（2026-10-11 用户要求）：欢迎横幅（衍衡 / 在线 · …）不再渲染 ——
 * 状态信息由悬浮球状态胶囊与侧栏承担。
 *
 * The identity header is gone from the conversation page (2026-10-11 user request): the
 * welcome banner (衍衡 / online · …) no longer renders — status lives on the float-ball
 * pill and the sidebar.
 */
describe('ConsoleMessageList 头部移除', () => {
  it('不渲染欢迎横幅（衍衡/在线状态行）', () => {
    const w = mount(ConsoleMessageList, { props: { messages: [] } })
    expect(w.find('.welcome').exists()).toBe(false)
    expect(w.text()).not.toContain('衍衡')
    expect(w.text()).not.toContain('语音唤醒已关')
  })

  it('空态提示仍在', () => {
    const w = mount(ConsoleMessageList, { props: { messages: [] } })
    expect(w.text()).toContain('还没有对话')
  })
})
