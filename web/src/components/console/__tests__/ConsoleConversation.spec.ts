// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('../../../api', () => ({ api: { createSession: vi.fn() }, streamUtter: vi.fn() }))
vi.mock('../../../composables/assistant/store', () => ({
  createNewSession: vi.fn(),
  switchSession: vi.fn(),
  // ConsoleConversation 的 canAct 计算读这两者（docs/designs/07）。
  state: { value: 'done' },
  currentSessionId: { value: 's1' },
}))
vi.mock('../../../composables/useAssistant', () => ({
  useAssistant: () => ({
    messages: { value: [] },
    pendingQuestion: { value: '' },
    sendText: vi.fn(),
    retryTool: vi.fn(),
    cancelTool: vi.fn(),
    forkAt: vi.fn(),
    sendEdited: vi.fn(),
    regenerate: vi.fn(),
  }),
}))

import ConsoleConversation from '../ConsoleConversation.vue'

/**
 * 对话页顶栏改版（2026-10-11）：「新建会话」移到左侧栏、「衍衡/在线」身份头移除 ——
 * 本组件只保留消息列表 + 输入框。
 * Conversation top-bar rework (2026-10-11): "New session" moved to the left sidebar and
 * the 衍衡/online identity header removed — this component is message list + input only.
 */
describe('ConsoleConversation 布局改版', () => {
  it('不渲染右上角新建按钮（已移至左侧栏）', () => {
    const w = mount(ConsoleConversation)
    expect(w.text()).not.toContain('新建会话')
    expect(w.find('.conv-top').exists()).toBe(false)
  })

  it('消息列表与输入框照常渲染', () => {
    const w = mount(ConsoleConversation)
    expect(w.find('.console-messages').exists()).toBe(true)
    expect(w.find('.console-input').exists()).toBe(true)
  })
})
