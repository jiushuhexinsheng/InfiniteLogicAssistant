// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

vi.mock('../../../api', () => ({
  api: { listLibrary: vi.fn(), getLibraryTask: vi.fn(), deleteLibraryTask: vi.fn() },
}))

import { api } from '../../../api'
import { notify } from '../../../composables/useToast'
import ConsoleLibrary from '../ConsoleLibrary.vue'

const TASKS = {
  ok: true,
  tasks: [
    { id: 1, goal: '复制文件到下载', params: { dest: '下载' },
      steps: [{ tool: 'write_file', args: { path: 'a.txt' }, status: 'ok' }],
      status: 'done', created: '2026-09-13T10:00:00', session_id: 's1' },
  ],
}

/** 任务库：列出存档 / 展开看 params 与 steps（只读）/ 删除。 */
describe('ConsoleLibrary', () => {
  beforeEach(() => {
    vi.mocked(api.listLibrary).mockReset()
    vi.mocked(api.listLibrary).mockResolvedValue(TASKS as any)
    vi.mocked(api.deleteLibraryTask).mockReset()
    vi.mocked(api.deleteLibraryTask).mockResolvedValue({ ok: true } as any)
    vi.restoreAllMocks()
  })

  /** 加载成功渲染任务目标。Loads and renders the archived goal. */
  it('加载成功渲染任务', async () => {
    const w = mount(ConsoleLibrary)
    await flushPromises()
    expect(w.text()).toContain('复制文件到下载')
    expect(w.text()).toContain('1 个参数')
  })

  /** 展开后显示参数与步骤（只读）。Expanding shows params and steps (read-only). */
  it('展开显示参数与步骤', async () => {
    const w = mount(ConsoleLibrary)
    await flushPromises()
    expect(w.find('.lib-detail').exists()).toBe(false)   // 初始收起
    await w.find('.lib-row').trigger('click')
    expect(w.find('.lib-detail').text()).toContain('下载')
    expect(w.find('.lib-detail').text()).toContain('write_file')
  })

  /** 加载失败展示错误提示（走统一错误处理）。A load failure surfaces the unified error note. */
  it('加载失败展示错误提示', async () => {
    vi.mocked(api.listLibrary).mockRejectedValue(new Error('库文件损坏'))
    const w = mount(ConsoleLibrary)
    await flushPromises()
    expect(w.find('.ui-errnote').text()).toBe('库文件损坏')
  })

  /** 空库显示空态文案。An empty library shows the empty-state copy. */
  it('空库显示空态', async () => {
    vi.mocked(api.listLibrary).mockResolvedValue({ ok: true, tasks: [] } as any)
    const w = mount(ConsoleLibrary)
    await flushPromises()
    expect(w.text()).toContain('暂无任务存档')
  })

  /** 删除失败弹出错误通知。A delete failure emits an error notice. */
  it('删除失败弹出错误通知', async () => {
    vi.mocked(api.deleteLibraryTask).mockRejectedValue(new Error('任务不存在'))
    const errSpy = vi.spyOn(notify, 'err')
    const w = mount(ConsoleLibrary)
    await flushPromises()
    await w.findAll('button').find((b) => b.text() === '删除')!.trigger('click')
    await flushPromises()
    expect(errSpy).toHaveBeenCalledWith('删除任务失败：任务不存在')
  })
})
