// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

vi.mock('../../../api', () => ({ api: { answer: vi.fn() }, streamUtter: vi.fn() }))

import { api } from '../../../api'
import { currentSessionId, pendingQuestion } from '../../../composables/assistant/store'
import QuestionCard from '../QuestionCard.vue'

/**
 * 提问卡片：confirm 类走结构化按钮，clarify 类走自由文本。
 * Question card: confirm questions use structured buttons, clarify questions use free text.
 *
 * 这是确认层安全的 UI 侧：只要 kind=confirm 一律渲染按钮，就不再依赖解析
 * 中文自由文本来判断「用户是否批准执行」。
 *
 * This is the UI side of the confirmation-safety work: kind=confirm always renders
 * buttons, so deciding "did the user approve execution" never depends on parsing
 * Chinese free text.
 */
describe('QuestionCard', () => {
  beforeEach(() => {
    pendingQuestion.value = null
    currentSessionId.value = ''
    vi.mocked(api.answer).mockReset()
    vi.mocked(api.answer).mockResolvedValue({ ok: true } as any)
  })

  /** 确认类提问：渲染「取消 / 确认」按钮，不渲染文本输入。 */
  it('confirm 类提问渲染按钮而非文本输入', () => {
    pendingQuestion.value = { text: '确认执行吗？删除 x', kind: 'confirm' }
    const w = mount(QuestionCard)
    expect(w.findAll('button').map((b) => b.text())).toEqual(['取消', '确认'])
    expect(w.find('input').exists()).toBe(false)
  })

  /** 点击「确认」→ 回传结构化 choice=yes（文本为空）。 */
  it('点击确认回传 choice=yes', async () => {
    currentSessionId.value = 's1'
    pendingQuestion.value = { text: '确认执行吗？', kind: 'confirm' }
    const w = mount(QuestionCard)
    await w.findAll('button').find((b) => b.text() === '确认')!.trigger('click')
    await flushPromises()
    expect(api.answer).toHaveBeenCalledWith('s1', '', 'yes')
  })

  /** 点击「取消」→ 回传结构化 choice=no。 */
  it('点击取消回传 choice=no', async () => {
    currentSessionId.value = 's1'
    pendingQuestion.value = { text: '确认执行吗？', kind: 'confirm' }
    const w = mount(QuestionCard)
    await w.findAll('button').find((b) => b.text() === '取消')!.trigger('click')
    await flushPromises()
    expect(api.answer).toHaveBeenCalledWith('s1', '', 'no')
  })

  /** 澄清类提问：保持原自由文本输入，不带 choice。 */
  it('clarify 类提问渲染文本输入且回答不带 choice', async () => {
    currentSessionId.value = 's1'
    pendingQuestion.value = { text: '目标位置？', kind: 'clarify' }
    const w = mount(QuestionCard)
    expect(w.find('input').exists()).toBe(true)
    await w.find('input').setValue('桌面')
    await w.findAll('button').find((b) => b.text() === '回答')!.trigger('click')
    await flushPromises()
    expect(api.answer).toHaveBeenCalledWith('s1', '桌面', undefined)
  })

  /** 无待答问题时整卡不渲染。The card renders nothing when no question is pending. */
  it('无待答问题时不渲染', () => {
    const w = mount(QuestionCard)
    expect(w.find('.confirm-card').exists()).toBe(false)
  })
})
