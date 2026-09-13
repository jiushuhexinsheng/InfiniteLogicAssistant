import { beforeEach, describe, expect, it, vi } from 'vitest'

// 只桩掉网络层，保留 store 真实实现（断言写入的消息）。
// Stub only the network layer, keeping the real store (to assert on the written message).
vi.mock('../../../api', () => ({
  api: { answer: vi.fn(), callTool: vi.fn() },
  streamUtter: vi.fn(),
}))
// runTurn 会调用 speakAuto（TTS）；此处桩掉以免依赖浏览器语音 API。
// runTurn calls speakAuto (TTS); stub it out so no browser speech API is needed.
vi.mock('../useTts', () => ({ speakAuto: vi.fn() }))

import { api, streamUtter } from '../../../api'
import { currentSessionId, messages, pendingQuestion } from '../store'
import { runTurn, sendAnswer } from '../useChat'

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

  /** 成功时不写入错误消息（正常会写入回答记录，但那不是错误消息）。
   *  No error message on success — the answer record itself is written, but that is not an error. */
  it('投递成功时不写入错误消息', async () => {
    currentSessionId.value = 's1'
    vi.mocked(api.answer).mockResolvedValue({ ok: true })
    await sendAnswer('是的')
    expect(messages.value.some((m) => m.role === 'system' || m.text.includes('失败'))).toBe(false)
  })

  /** 结构化确认：空文本 + choice 也应投递（按钮回答不带文本）。 */
  it('结构化确认允许空文本并透传 choice', async () => {
    currentSessionId.value = 's1'
    vi.mocked(api.answer).mockResolvedValue({ ok: true })
    await sendAnswer('', 'yes')
    expect(api.answer).toHaveBeenCalledWith('s1', '', 'yes')
  })

  /** 既无文本也无 choice 时不投递（避免空回答解除后端阻塞）。 */
  it('既无文本也无 choice 时不投递', async () => {
    currentSessionId.value = 's1'
    await sendAnswer('   ')
    expect(api.answer).not.toHaveBeenCalled()
  })

  /** 任意字符串 choice 都能透传（权限策略的 once / always 等）。 */
  it('任意字符串 choice 均可透传', async () => {
    currentSessionId.value = 's1'
    vi.mocked(api.answer).mockResolvedValue({ ok: true })
    await sendAnswer('', 'always')
    expect(api.answer).toHaveBeenCalledWith('s1', '', 'always')
  })
})

/** 问答进入聊天记录（需求 6）。Questions and answers enter the chat record. */
describe('useChat 问答入聊天记录', () => {
  beforeEach(() => {
    messages.value = []
    currentSessionId.value = ''
    pendingQuestion.value = null
    vi.mocked(api.answer).mockReset()
    vi.mocked(api.answer).mockResolvedValue({ ok: true })
    vi.mocked(streamUtter).mockReset()
  })

  /** 提问以 assistant 角色 + ❓ 前缀入记录（经 runTurn 真实入口）。 */
  it('提问以 assistant 角色入聊天记录', async () => {
    vi.mocked(streamUtter).mockImplementation(async (_t: string, h: any) => {
      h.onQuestion?.({ question: '确认执行吗？', session_id: 's1', kind: 'choice',
                       options: [{ value: 'yes', label: '确认' }] })
      return 's1'
    })
    messages.value = [{ id: 'm1', role: 'user', text: '做事', timestamp: Date.now() }]
    await runTurn()
    const q = messages.value.find((m) => m.role === 'assistant')
    expect(q?.text).toBe('❓ 确认执行吗？')
  })

  /** 选择类回答：以被选 option 的 label 入记录（不写机器值）。 */
  it('选择类回答以 label 入聊天记录', async () => {
    currentSessionId.value = 's1'
    pendingQuestion.value = {
      text: '确认执行吗？', kind: 'choice',
      options: [{ value: 'yes', label: '确认' }, { value: 'no', label: '取消' }],
    }
    await sendAnswer('', 'yes')
    const last = messages.value[messages.value.length - 1]
    expect(last?.role).toBe('user')
    expect(last?.text).toBe('确认')
  })

  /** 文本类回答：以输入文本入记录。 */
  it('文本类回答以输入文本入聊天记录', async () => {
    currentSessionId.value = 's1'
    pendingQuestion.value = { text: '目标位置？', kind: 'text', options: [] }
    await sendAnswer('桌面')
    const last = messages.value[messages.value.length - 1]
    expect(last?.role).toBe('user')
    expect(last?.text).toBe('桌面')
  })

  /** 投递失败时不写回答记录（避免记录与后端状态不一致）。 */
  it('投递失败时不写回答记录', async () => {
    currentSessionId.value = 's1'
    pendingQuestion.value = { text: '目标位置？', kind: 'text', options: [] }
    vi.mocked(api.answer).mockRejectedValue(new Error('会话已失效'))
    await sendAnswer('桌面')
    expect(messages.value.some((m) => m.text === '桌面')).toBe(false)
  })
})
