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

  /**
   * 确认类提问：本视图必须与对话视图一致地渲染结构化按钮。
   * 否则用户在这里看到输入框、输入「确定」等自由文本，而后端只接受精确的
   * 「确认」——自由文本会被判为拒绝并取消任务（此为改造后引入的回归）。
   *
   * Confirmation questions must render structured buttons here exactly as the
   * conversation view does. Otherwise the user sees a text box, types free text
   * such as "确定", and the backend — which only accepts an exact "确认" — rejects
   * it and cancels the task (a regression introduced by the structured-confirmation change).
   */
  it('确认类提问渲染结构化按钮且不提供输入框', async () => {
    vi.mocked(streamUtter).mockImplementation(async (_t: string, h: any) => {
      h.onQuestion?.({ question: '确认执行吗？', session_id: 's1', kind: 'confirm' })
      return 's1'
    })
    const w = mount(ConsoleTaskView)
    await w.find('textarea').setValue('删文件')
    await w.findAll('button').find((b) => b.text() === '发送')!.trigger('click')
    await flushPromises()

    const card = w.find('.confirm-card')
    expect(card.exists()).toBe(true)
    expect(card.findAll('button').map((b) => b.text())).toEqual(['取消', '确认'])
    expect(card.find('input').exists()).toBe(false)
  })

  /** 点击「确认」→ 回传结构化 choice=yes。 */
  it('点击确认回传结构化 choice=yes', async () => {
    vi.mocked(streamUtter).mockImplementation(async (_t: string, h: any) => {
      h.onQuestion?.({ question: '确认执行吗？', session_id: 's1', kind: 'confirm' })
      return 's1'
    })
    vi.mocked(api.answer).mockResolvedValue({ ok: true } as any)
    const w = mount(ConsoleTaskView)
    await w.find('textarea').setValue('删文件')
    await w.findAll('button').find((b) => b.text() === '发送')!.trigger('click')
    await flushPromises()

    await w.findAll('button').find((b) => b.text() === '确认')!.trigger('click')
    await flushPromises()
    expect(api.answer).toHaveBeenCalledWith('s1', '', 'yes')
  })
})

/**
 * session_id 的获取时机：作答发生在流【进行中】，而 streamUtter 的返回值要等流结束才有。
 * 因此必须从事件回调里捕获 session_id —— 否则作答会打到空 session 上（404），
 * 「任务」tab 将完全无法回答任何提问，停止按钮同样失效。
 *
 * When session_id becomes available: answering happens while the stream is still
 * running, whereas streamUtter's return value only arrives once it ends. The id must
 * therefore be captured from the event callbacks — otherwise answers hit an empty
 * session (404), leaving the Task tab unable to answer any question at all (and the
 * stop button equally broken).
 */
describe('ConsoleTaskView session_id 捕获时机', () => {
  beforeEach(() => {
    vi.mocked(api.answer).mockReset()
    vi.mocked(api.answer).mockResolvedValue({ ok: true } as any)
    vi.mocked(api.stopTask).mockReset()
    vi.mocked(api.stopTask).mockResolvedValue({ ok: true } as any)
    vi.mocked(streamUtter).mockReset()
  })

  /** 模拟真实时序：流阻塞等待作答，期间 streamUtter 尚未返回。 */
  function pendingStream(onQuestion: Record<string, unknown>) {
    let release!: (v: string) => void
    vi.mocked(streamUtter).mockImplementation(((_t: string, h: any) => {
      h.onQuestion?.(onQuestion)
      return new Promise<string>((r) => { release = r })
    }) as any)
    return () => release('s-live')
  }

  /** 澄清作答必须用事件里的 session_id，而不是尚未赋值的本地 ref。 */
  it('澄清作答使用事件携带的 session_id', async () => {
    const release = pendingStream({ question: '目标位置？', session_id: 's-live', kind: 'clarify' })
    const w = mount(ConsoleTaskView)
    await w.find('textarea').setValue('删文件')
    await w.findAll('button').find((b) => b.text() === '发送')!.trigger('click')
    await flushPromises()

    await w.find('.confirm-card input').setValue('桌面')
    await w.findAll('button').find((b) => b.text() === '回答')!.trigger('click')
    await flushPromises()
    expect(api.answer).toHaveBeenCalledWith('s-live', '桌面')
    release()
  })

  /** 结构化确认同样必须用事件里的 session_id。 */
  it('结构化确认使用事件携带的 session_id', async () => {
    const release = pendingStream({ question: '确认执行吗？', session_id: 's-live', kind: 'confirm' })
    const w = mount(ConsoleTaskView)
    await w.find('textarea').setValue('删文件')
    await w.findAll('button').find((b) => b.text() === '发送')!.trigger('click')
    await flushPromises()

    await w.findAll('button').find((b) => b.text() === '确认')!.trigger('click')
    await flushPromises()
    expect(api.answer).toHaveBeenCalledWith('s-live', '', 'yes')
    release()
  })

  /** 停止按钮依赖 sessionId：流进行中就必须可用。 */
  it('流进行中停止按钮即可用并使用事件携带的 session_id', async () => {
    const release = pendingStream({ question: '目标位置？', session_id: 's-live', kind: 'clarify' })
    const w = mount(ConsoleTaskView)
    await w.find('textarea').setValue('删文件')
    await w.findAll('button').find((b) => b.text() === '发送')!.trigger('click')
    await flushPromises()

    const stopBtn = w.findAll('button').find((b) => b.text() === '停止')
    expect(stopBtn, '流进行中应显示停止按钮').toBeTruthy()
    await stopBtn!.trigger('click')
    await flushPromises()
    expect(api.stopTask).toHaveBeenCalledWith('s-live')
    release()
  })
})
