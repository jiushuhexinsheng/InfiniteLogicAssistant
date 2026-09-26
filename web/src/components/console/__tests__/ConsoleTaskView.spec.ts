// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

vi.mock('../../../api', () => ({
  api: { answer: vi.fn(), stopTask: vi.fn(), callTool: vi.fn() },
  streamUtter: vi.fn(),
}))
vi.mock('../../../composables/assistant/useTts', () => ({ speakAuto: vi.fn() }))

import { api, streamUtter } from '../../../api'
import { messages, currentSessionId, pendingQuestion, state } from '../../../composables/assistant/store'
import ConsoleTaskView from '../ConsoleTaskView.vue'

const CONFIRM_OPTIONS = [{ value: 'yes', label: '确认' }, { value: 'no', label: '取消' }]

/**
 * 任务视图已收敛：独立流消费与重复问题卡删除，共享 useChat + BlockHost(task 皮肤)。
 * 这些用例钉住收敛后仍然成立的保障：确认类只出按钮、事件期 session_id/qid 可用、
 * 停止按钮流中可用。
 *
 * The task view is converged: the private stream and duplicate question card are
 * gone, sharing useChat + BlockHost (task skin). These cases pin the guarantees
 * that must still hold: choice questions render buttons only, session_id/qid are
 * available while the stream is running, and the stop button works mid-stream.
 */
describe('ConsoleTaskView 收敛后（共享块协议）', () => {
  beforeEach(() => {
    messages.value = []
    currentSessionId.value = ''
    pendingQuestion.value = null
    state.value = 'idle'
    vi.mocked(api.answer).mockReset()
    vi.mocked(api.answer).mockResolvedValue({ ok: true } as any)
    vi.mocked(api.stopTask).mockReset()
    vi.mocked(api.stopTask).mockResolvedValue({ ok: true } as any)
    vi.mocked(streamUtter).mockReset()
  })

  /** 模拟真实时序的流：onEvent 先于具体回调；流在 onDone 前保持打开。 */
  function turnStream(events: Array<Record<string, unknown>>) {
    let release!: (v: string) => void
    vi.mocked(streamUtter).mockImplementation(((_t: string, h: any) => {
      for (const evt of events) {
        h.onEvent?.(evt)
        if (evt.type === 'question') {
          h.onQuestion?.({ question: evt.question, session_id: evt.session_id,
                           kind: evt.kind, options: evt.options, qid: evt.qid })
        }
      }
      return new Promise<string>((r) => { release = r })
    }) as any)
    return () => { release('s-live'); }
  }

  /** 确认类提问渲染结构化按钮且不提供输入框（确认安全 UI 不变式）。
   *  Choice questions render structured buttons and no input (confirmation-safety invariant). */
  it('确认类提问渲染结构化按钮且不提供输入框', async () => {
    const release = turnStream([
      { type: 'question', question: '确认执行吗？', session_id: 's1', kind: 'choice',
        options: CONFIRM_OPTIONS, qid: 'q1' },
    ])
    const w = mount(ConsoleTaskView, { attachTo: document.body })
    await w.find('textarea').setValue('删文件')
    await w.findAll('button').find((b) => b.text() === '发送')!.trigger('click')
    await flushPromises()

    const card = w.find('.blk-question')
    expect(card.exists()).toBe(true)
    expect(card.findAll('button').map((b) => b.text())).toEqual(['确认', '取消'])
    expect(card.find('input').exists()).toBe(false)
    release()
    w.unmount()
  })

  /** 点击「确认」→ api.answer 收到事件期 session_id + choice=yes + qid。
   *  Clicking 确认 delivers the event-captured session_id + choice=yes + qid. */
  it('点击确认回传结构化 choice 与事件期 session_id/qid', async () => {
    const release = turnStream([
      { type: 'question', question: '确认执行吗？', session_id: 's-live', kind: 'choice',
        options: CONFIRM_OPTIONS, qid: 'q-live' },
    ])
    const w = mount(ConsoleTaskView, { attachTo: document.body })
    await w.find('textarea').setValue('删文件')
    await w.findAll('button').find((b) => b.text() === '发送')!.trigger('click')
    await flushPromises()

    await w.findAll('button').find((b) => b.text() === '确认')!.trigger('click')
    await flushPromises()
    expect(api.answer).toHaveBeenCalledWith('s-live', '', 'yes', expect.objectContaining({ qid: 'q-live' }))
    release()
    w.unmount()
  })

  /** 流进行中停止按钮可用并使用事件携带的 session_id。 */
  it('流进行中停止按钮可用并使用事件携带的 session_id', async () => {
    const release = turnStream([
      { type: 'question', question: '目标位置？', session_id: 's-live', kind: 'text', qid: 'q2' },
    ])
    const w = mount(ConsoleTaskView, { attachTo: document.body })
    await w.find('textarea').setValue('删文件')
    await w.findAll('button').find((b) => b.text() === '发送')!.trigger('click')
    await flushPromises()

    const stopBtn = w.findAll('button').find((b) => b.text() === '停止')
    expect(stopBtn, '流进行中应显示停止按钮').toBeTruthy()
    await stopBtn!.trigger('click')
    await flushPromises()
    expect(api.stopTask).toHaveBeenCalledWith('s-live')
    release()
    w.unmount()
  })
})
