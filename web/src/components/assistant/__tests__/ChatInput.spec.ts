// @vitest-environment jsdom
/** 聊天输入：模型切换器在输入行左侧；Enter 发送。Chat input: model picker on the left; Enter sends. */
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('../ModelPicker.vue', () => ({
  default: { template: '<div class="model-picker-stub" />' },
}))

import ChatInput from '../ChatInput.vue'
import { state as asstState } from '../../../composables/assistant/store'
import { resetPause } from '../../../composables/assistant/useChatPause'

describe('ChatInput', () => {
  it('输入行渲染模型切换器', () => {
    const w = mount(ChatInput)
    expect(w.find('.chat-input-row .model-picker-stub').exists()).toBe(true)
  })

  /** 回合进行中：模型切换器让位给暂停/停止，避免把窄输入框挤成一条缝。
   *  While a turn runs the model picker yields to pause/stop so the narrow textarea
   *  is not pinched. */
  it('回合进行中隐藏模型切换器并显示暂停/停止', async () => {
    asstState.value = 'responding'
    const w = mount(ChatInput)
    expect(w.find('.chat-input-row .model-picker-stub').exists()).toBe(false)
    expect(w.find('[data-run="pause"]').exists()).toBe(true)
    expect(w.find('[data-run="stop"]').exists()).toBe(true)
    asstState.value = 'idle'
    resetPause()
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
