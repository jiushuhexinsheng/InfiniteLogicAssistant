// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

vi.mock('../../../api', () => ({
  api: { getSchedules: vi.fn(), addSchedule: vi.fn(), deleteSchedule: vi.fn() },
}))

import { api } from '../../../api'
import { notify } from '../../../composables/useToast'
import ConsoleScheduleView from '../ConsoleScheduleView.vue'

const SCHEDULES = { ok: true, schedules: [{ id: 's1', cron: '0 9 * * *', prompt: '查天气' }] }

/** 定时任务列表的加载与操作错误处理。Load and action error handling for the schedule list. */
describe('ConsoleScheduleView', () => {
  beforeEach(() => {
    vi.mocked(api.getSchedules).mockReset()
    vi.mocked(api.addSchedule).mockReset()
    vi.mocked(api.deleteSchedule).mockReset()
    vi.restoreAllMocks()
  })

  /** 成功：渲染 cron 与内容。Success: renders the cron expression and prompt. */
  it('加载成功渲染定时任务', async () => {
    vi.mocked(api.getSchedules).mockResolvedValue(SCHEDULES as any)
    const w = mount(ConsoleScheduleView)
    await flushPromises()
    expect(w.text()).toContain('0 9 * * *')
    expect(w.text()).toContain('查天气')
  })

  /** 加载失败：展示错误提示（原先只写 console.error）。Load failure: shows the error note (previously console only). */
  it('加载失败展示错误提示', async () => {
    vi.mocked(api.getSchedules).mockRejectedValue(new Error('调度器离线'))
    const w = mount(ConsoleScheduleView)
    await flushPromises()
    expect(w.find('.ui-errnote').text()).toBe('调度器离线')
  })

  /** 取消失败：弹出错误通知（原先静默）。Delete failure: emits an error notice (previously silent). */
  it('取消定时任务失败弹出错误通知', async () => {
    vi.mocked(api.getSchedules).mockResolvedValue(SCHEDULES as any)
    vi.mocked(api.deleteSchedule).mockRejectedValue(new Error('任务不存在'))
    const errSpy = vi.spyOn(notify, 'err')
    const w = mount(ConsoleScheduleView)
    await flushPromises()
    const del = w.findAll('button').find((b) => b.text() === '删除')
    await del!.trigger('click')
    await flushPromises()
    expect(errSpy).toHaveBeenCalledWith('取消定时任务失败：任务不存在')
  })
})
