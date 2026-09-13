// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

vi.mock('../../../api', () => ({ api: { createSession: vi.fn() }, streamUtter: vi.fn() }))
vi.mock('../../../composables/assistant/store', () => ({
  createNewSession: vi.fn(),
  switchSession: vi.fn(),
}))
vi.mock('../../../composables/useAssistant', () => ({
  useAssistant: () => ({
    messages: { value: [] },
    wakeHint: { value: '「衍衡」或「洛吉斯」' },
    // ChatInput 需要 pendingQuestion 决定是否显示回答框 / ChatInput needs it to decide whether to show the answer box
    pendingQuestion: { value: '' },
    sendText: vi.fn(),
    retryTool: vi.fn(),
    cancelTool: vi.fn(),
  }),
}))

import { api } from '../../../api'
import { notify } from '../../../composables/useToast'
import { createNewSession } from '../../../composables/assistant/store'
import ConsoleConversation from '../ConsoleConversation.vue'

/** 新建会话按钮的错误处理（原先 catch 后完全静默）。
 *  Error handling for the new-session button (previously a fully silent catch). */
describe('ConsoleConversation 新建会话', () => {
  beforeEach(() => {
    vi.mocked(api.createSession).mockReset()
    vi.mocked(createNewSession).mockReset()
    vi.restoreAllMocks()
  })

  /** 成功：切换会话并提示。Success: switches the session and notifies. */
  it('新建会话成功时提示并切换', async () => {
    vi.mocked(api.createSession).mockResolvedValue({ ok: true, session: { id: 's9' } } as any)
    const okSpy = vi.spyOn(notify, 'ok')
    const w = mount(ConsoleConversation)
    await w.find('button').trigger('click')
    await flushPromises()
    expect(createNewSession).toHaveBeenCalledWith('s9')
    expect(okSpy).toHaveBeenCalledWith('已新建会话')
  })

  /** 失败：弹出错误通知，而非静默无反应。Failure: emits an error notice instead of silently doing nothing. */
  it('新建会话失败时弹出错误通知', async () => {
    vi.mocked(api.createSession).mockRejectedValue(new Error('会话数超限'))
    const errSpy = vi.spyOn(notify, 'err')
    const w = mount(ConsoleConversation)
    await w.find('button').trigger('click')
    await flushPromises()
    expect(errSpy).toHaveBeenCalledWith('新建会话失败：会话数超限')
    expect(createNewSession).not.toHaveBeenCalled()
  })
})
