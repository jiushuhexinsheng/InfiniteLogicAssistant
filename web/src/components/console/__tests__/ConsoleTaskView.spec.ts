// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

vi.mock('../../../api', () => ({
  api: { answer: vi.fn(), stopTask: vi.fn() },
  streamUtter: vi.fn(),
}))

import { api, streamUtter } from '../../../api'
import ConsoleTaskView from '../ConsoleTaskView.vue'

/**
 * 任务视图的错误文案（保留任务日志语义，仅统一 formatError 与标点）。
 * Error text in the task view (keeps the task-log semantics, only unifying formatError and punctuation).
 */
describe('ConsoleTaskView 任务日志错误文案', () => {
  beforeEach(() => {
    vi.mocked(api.answer).mockReset()
    vi.mocked(streamUtter).mockReset()
    vi.restoreAllMocks()
  })

  /** 回答投递失败：写入任务日志（不是 toast —— 该组件的错误本就归档在日志里）。 */
  it('回答投递失败时写入统一格式的任务日志', async () => {
    // 模拟一次会抛出澄清问题的 SSE 轮次 / Simulate an SSE turn that raises a clarification question
    vi.mocked(streamUtter).mockImplementation(async (_t: string, h: any) => {
      h.onQuestion?.({ question: '确认执行吗', session_id: 's1' })
      return 's1'
    })
    vi.mocked(api.answer).mockRejectedValue(new Error('会话已失效'))

    const w = mount(ConsoleTaskView)
    // 发一条指令，进入有 sessionId + pendingQuestion 的状态
    await w.find('textarea').setValue('做事')
    await w.findAll('button').find((b) => b.text() === '发送')!.trigger('click')
    await flushPromises()

    // 回答问题 → 投递失败 → 日志出现统一格式的错误行
    await w.find('input').setValue('确认')
    await w.findAll('button').find((b) => b.text() === '回答')!.trigger('click')
    await flushPromises()

    expect(w.text()).toContain('❌ 回答投递失败：会话已失效')
  })
})
