// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

vi.mock('../../../api', () => ({ api: { answer: vi.fn() }, streamUtter: vi.fn() }))

import { api } from '../../../api'
import { currentSessionId, pendingQuestion } from '../../../composables/assistant/store'
import type { QuestionOption } from '../../../types'
import QuestionCard from '../QuestionCard.vue'

/** 确认类选项（原先的 confirm 已并入 choice）。Confirmation options (the former confirm folded into choice). */
const CONFIRM_OPTIONS: QuestionOption[] = [
  { value: 'yes', label: '确认' },
  { value: 'no', label: '取消' },
]

/**
 * 提问卡片按 kind 三态渲染：text 输入框 / choice 按钮 / composite 按钮加输入框。
 * Question card renders three states by kind: text (input) / choice (buttons) /
 * composite (buttons plus input).
 *
 * 这是确认层安全的 UI 侧：choice 类一律渲染按钮且不给输入框，判定「用户是否
 * 批准执行」就永不依赖解析中文自由文本。
 *
 * This is the UI side of the confirmation-safety work: a choice question always renders
 * buttons and no input, so deciding "did the user approve execution" never depends on
 * parsing Chinese free text.
 */
describe('QuestionCard', () => {
  beforeEach(() => {
    pendingQuestion.value = null
    currentSessionId.value = ''
    vi.mocked(api.answer).mockReset()
    vi.mocked(api.answer).mockResolvedValue({ ok: true } as any)
  })

  /** 选择类提问：渲染选项按钮，不渲染文本输入。 */
  it('choice 类提问渲染选项按钮而非文本输入', () => {
    pendingQuestion.value = { text: '确认执行吗？删除 x', kind: 'choice', options: CONFIRM_OPTIONS }
    const w = mount(QuestionCard)
    expect(w.findAll('button').map((b) => b.text())).toEqual(['确认', '取消'])
    expect(w.find('input').exists()).toBe(false)
  })

  /** 点击「确认」→ 回传结构化 choice=yes（文本为空）。 */
  it('点击确认回传 choice=yes', async () => {
    currentSessionId.value = 's1'
    pendingQuestion.value = { text: '确认执行吗？', kind: 'choice', options: CONFIRM_OPTIONS }
    const w = mount(QuestionCard)
    await w.findAll('button').find((b) => b.text() === '确认')!.trigger('click')
    await flushPromises()
    expect(api.answer).toHaveBeenCalledWith('s1', '', 'yes')
  })

  /** 点击「取消」→ 回传结构化 choice=no。 */
  it('点击取消回传 choice=no', async () => {
    currentSessionId.value = 's1'
    pendingQuestion.value = { text: '确认执行吗？', kind: 'choice', options: CONFIRM_OPTIONS }
    const w = mount(QuestionCard)
    await w.findAll('button').find((b) => b.text() === '取消')!.trigger('click')
    await flushPromises()
    expect(api.answer).toHaveBeenCalledWith('s1', '', 'no')
  })

  /** 文本类提问：渲染自由文本输入，回答不带 choice。 */
  it('text 类提问渲染文本输入且回答不带 choice', async () => {
    currentSessionId.value = 's1'
    pendingQuestion.value = { text: '目标位置？', kind: 'text', options: [] }
    const w = mount(QuestionCard)
    expect(w.find('input').exists()).toBe(true)
    await w.find('input').setValue('桌面')
    await w.findAll('button').find((b) => b.text() === '回答')!.trigger('click')
    await flushPromises()
    expect(api.answer).toHaveBeenCalledWith('s1', '桌面', undefined)
  })

  /** 综合类：按钮 + 输入框，只点按钮即可提交。 */
  it('composite 类只点按钮即可提交', async () => {
    currentSessionId.value = 's1'
    pendingQuestion.value = {
      text: '选一个并补充说明', kind: 'composite',
      options: [{ value: 'a', label: '甲' }, { value: 'b', label: '乙' }],
    }
    const w = mount(QuestionCard)
    expect(w.find('input').exists()).toBe(true)
    await w.findAll('button').find((b) => b.text() === '甲')!.trigger('click')
    await flushPromises()
    expect(api.answer).toHaveBeenCalledWith('s1', '', 'a')
  })

  /** 综合类：只输文本也可提交（不带 choice）。 */
  it('composite 类只输文本即可提交', async () => {
    currentSessionId.value = 's1'
    pendingQuestion.value = {
      text: '选一个并补充说明', kind: 'composite',
      options: [{ value: 'a', label: '甲' }],
    }
    const w = mount(QuestionCard)
    await w.find('input').setValue('我补充一下')
    await w.findAll('button').find((b) => b.text() === '回答')!.trigger('click')
    await flushPromises()
    expect(api.answer).toHaveBeenCalledWith('s1', '我补充一下', undefined)
  })

  /** 无待答问题时整卡不渲染。The card renders nothing when no question is pending. */
  it('无待答问题时不渲染', () => {
    const w = mount(QuestionCard)
    expect(w.find('.confirm-card').exists()).toBe(false)
  })
})
