import { beforeEach, describe, expect, it, vi } from 'vitest'

// 只桩掉网络层，保留 store 真实实现（断言写入的消息）。
// Stub only the network layer, keeping the real store (to assert on the written message).
vi.mock('../../../api', () => ({
  api: { answer: vi.fn(), callTool: vi.fn() },
  streamUtter: vi.fn(),
}))

import { api } from '../../../api'
import { currentSessionId, messages } from '../store'
import { sendAnswer } from '../useChat'

/** useChat 回答投递的错误文案。Error text for useChat's answer delivery. */
describe('useChat sendAnswer 错误处理', () => {
  beforeEach(() => {
    messages.value = []
    currentSessionId.value = ''
    vi.mocked(api.answer).mockReset()
  })

  /** 失败写入系统消息：文案统一走 formatError，标点为全角。 */
  it('回答投递失败时写入统一格式的系统消息', async () => {
    currentSessionId.value = 's1'
    vi.mocked(api.answer).mockRejectedValue(new Error('连接被重置'))
    await sendAnswer('是的')
    const last = messages.value[messages.value.length - 1]
    expect(last?.role).toBe('system')
    expect(last?.text).toBe('回答投递失败：连接被重置')
  })

  /** 非 Error 的拒绝原因不应渲染成空串。 */
  it('非 Error 拒绝原因回退为「未知错误」而非空串', async () => {
    currentSessionId.value = 's1'
    vi.mocked(api.answer).mockRejectedValue(null)
    await sendAnswer('是的')
    expect(messages.value[messages.value.length - 1]?.text).toBe('回答投递失败：未知错误')
  })

  /** 成功时不写入任何错误消息。 */
  it('投递成功时不写入错误消息', async () => {
    currentSessionId.value = 's1'
    vi.mocked(api.answer).mockResolvedValue({ ok: true })
    await sendAnswer('是的')
    expect(messages.value).toHaveLength(0)
  })
})
