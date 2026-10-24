// @vitest-environment jsdom
/** 聊天输入：模型切换器在输入行左侧；Enter 发送。Chat input: model picker on the left; Enter sends. */
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('../ModelPicker.vue', () => ({
  default: { template: '<div class="model-picker-stub" />' },
}))

import ChatInput from '../ChatInput.vue'

describe('ChatInput', () => {
  it('输入行渲染模型切换器', () => {
    const w = mount(ChatInput)
    expect(w.find('.chat-input-row .model-picker-stub').exists()).toBe(true)
  })

  it('输入文本后 Enter 发送并清空', async () => {
    const w = mount(ChatInput)
    const ta = w.find('textarea')
    await ta.setValue('你好')

    await ta.trigger('keydown', { key: 'Enter' })

    expect(w.emitted('send')?.[0]).toEqual(['你好'])
    expect((ta.element as HTMLTextAreaElement).value).toBe('')
  })
})
