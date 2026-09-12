// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

vi.mock('../../../api', () => ({ api: { getMemory: vi.fn(), deleteMemory: vi.fn() } }))

import { api } from '../../../api'
import { notify } from '../../../composables/useToast'
import ConsoleMemoryView from '../ConsoleMemoryView.vue'

const FACTS = { ok: true, facts: [{ topic: '偏好', content: '喜欢深色主题', ts: '2026-09-12', source: 'task:t1' }] }

/** 记忆列表的加载与删除错误处理。Load and delete error handling for the memory list. */
describe('ConsoleMemoryView', () => {
  beforeEach(() => {
    vi.mocked(api.getMemory).mockReset()
    vi.mocked(api.deleteMemory).mockReset()
    vi.restoreAllMocks()
  })

  /** 成功：渲染记忆内容。Success: renders the memory content. */
  it('加载成功渲染记忆列表', async () => {
    vi.mocked(api.getMemory).mockResolvedValue(FACTS as any)
    const w = mount(ConsoleMemoryView)
    await flushPromises()
    expect(w.text()).toContain('喜欢深色主题')
  })

  /** 加载失败：展示错误提示（原先只写 console.error，界面完全看不到）。
   *  Load failure: shows the error note (previously console.error only, invisible in the UI). */
  it('加载失败展示错误提示', async () => {
    vi.mocked(api.getMemory).mockRejectedValue(new Error('数据库被占用'))
    const w = mount(ConsoleMemoryView)
    await flushPromises()
    expect(w.find('.ui-errnote').text()).toBe('数据库被占用')
  })

  /** 删除失败：弹出错误通知（原先静默）。Delete failure: emits an error notice (previously silent). */
  it('删除失败弹出错误通知', async () => {
    vi.mocked(api.getMemory).mockResolvedValue(FACTS as any)
    vi.mocked(api.deleteMemory).mockRejectedValue(new Error('删除被拒'))
    const errSpy = vi.spyOn(notify, 'err')
    const w = mount(ConsoleMemoryView)
    await flushPromises()
    const del = w.findAll('button').find((b) => b.text() === '删除')
    await del!.trigger('click')
    await flushPromises()
    expect(errSpy).toHaveBeenCalledWith('删除记忆失败：删除被拒')
  })
})
