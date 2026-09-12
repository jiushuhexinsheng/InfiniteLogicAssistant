// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

vi.mock('../../../api', () => ({
  api: {
    listSessions: vi.fn(), createSession: vi.fn(), getHistoryDetail: vi.fn(),
    clearSession: vi.fn(), archiveSession: vi.fn(), deleteSession: vi.fn(), renameSession: vi.fn(),
  },
}))

import { api } from '../../../api'
import { notify } from '../../../composables/useToast'
import ConsoleHistory from '../ConsoleHistory.vue'

const SESSIONS = {
  ok: true,
  sessions: [{ id: 's1', name: '会话一', updated: '2026-09-12T10:00:00', message_count: 3, summary: '聊了天气', archived: false }],
}

/** 会话列表的加载与操作错误处理（原先 7 处 catch 全部静默）。
 *  Load and action error handling for the session list (all 7 catches were previously silent). */
describe('ConsoleHistory', () => {
  beforeEach(() => {
    for (const fn of Object.values(vi.mocked(api))) vi.mocked(fn).mockReset()
    vi.restoreAllMocks()
  })

  /** 成功：渲染会话名与摘要。Success: renders the session name and summary. */
  it('加载成功渲染会话列表', async () => {
    vi.mocked(api.listSessions).mockResolvedValue(SESSIONS as any)
    const w = mount(ConsoleHistory)
    await flushPromises()
    expect(w.text()).toContain('会话一')
    expect(w.text()).toContain('聊了天气')
  })

  /** 加载失败：展示错误提示。Load failure: shows the error note. */
  it('加载失败展示错误提示', async () => {
    vi.mocked(api.listSessions).mockRejectedValue(new Error('后端未就绪'))
    const w = mount(ConsoleHistory)
    await flushPromises()
    expect(w.find('.ui-errnote').text()).toBe('后端未就绪')
  })

  /** 删除失败：弹出错误通知而非静默吞掉。Delete failure: emits an error notice instead of swallowing it. */
  it('删除会话失败弹出错误通知', async () => {
    vi.mocked(api.listSessions).mockResolvedValue(SESSIONS as any)
    vi.mocked(api.deleteSession).mockRejectedValue(new Error('会话受保护'))
    const errSpy = vi.spyOn(notify, 'err')
    const w = mount(ConsoleHistory)
    await flushPromises()
    const del = w.findAll('button').find((b) => b.text() === '删除')
    await del!.trigger('click')
    await flushPromises()
    expect(errSpy).toHaveBeenCalledWith('删除会话失败：会话受保护')
  })

  /** 归档成功：弹出成功通知并刷新列表。Archive success: emits a success notice and refreshes the list. */
  it('归档成功弹出成功通知', async () => {
    vi.mocked(api.listSessions).mockResolvedValue(SESSIONS as any)
    vi.mocked(api.archiveSession).mockResolvedValue({ ok: true } as any)
    const okSpy = vi.spyOn(notify, 'ok')
    const w = mount(ConsoleHistory)
    await flushPromises()
    const arch = w.findAll('button').find((b) => b.text() === '归档')
    await arch!.trigger('click')
    await flushPromises()
    expect(okSpy).toHaveBeenCalledWith('归档成功')
  })
})
