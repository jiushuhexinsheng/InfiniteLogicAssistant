// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

vi.mock('../../../api', () => ({ api: { getUploadStats: vi.fn() } }))

import { api } from '../../../api'
import ConsoleStats from '../ConsoleStats.vue'

const STATS = {
  ok: true,
  total: 4,
  by_via: { wake: 2, transcribe: 1, 'call-segment': 1 },
  days: [
    { date: '2026-10-01', wake: 1, transcribe: 1, 'call-segment': 0 },
    { date: '2026-10-02', wake: 0, transcribe: 0, 'call-segment': 1 },
    { date: '2026-10-03', wake: 0, transcribe: 0, 'call-segment': 0 },
    { date: '2026-10-04', wake: 0, transcribe: 0, 'call-segment': 0 },
    { date: '2026-10-05', wake: 0, transcribe: 0, 'call-segment': 0 },
    { date: '2026-10-06', wake: 0, transcribe: 0, 'call-segment': 0 },
    { date: '2026-10-07', wake: 1, transcribe: 0, 'call-segment': 0 },
  ],
}

/** 成本仪表：audio-upload via= 三前缀计数 + 近 7 日趋势挂进统计页。Cost dashboard:
 *  the three audio-upload via= counts + 7-day trend on the stats tab. */
describe('ConsoleStats 成本仪表', () => {
  beforeEach(() => {
    vi.mocked(api.getUploadStats).mockReset()
    vi.restoreAllMocks()
  })

  /** 挂载即拉取统计数据。Fetches stats on mount. */
  it('挂载时加载上传统计并渲染三前缀计数与合计', async () => {
    vi.mocked(api.getUploadStats).mockResolvedValue(STATS as any)
    const w = mount(ConsoleStats)
    await flushPromises()
    expect(api.getUploadStats).toHaveBeenCalledTimes(1)
    const t = w.text()
    expect(t).toContain('唤醒上传') && expect(t).toContain('2')
    expect(t).toContain('转写上传')
    expect(t).toContain('通话上传')
    expect(t).toContain('上传合计')
    expect(t).toContain('4')   // total
  })

  /** 近 7 日趋势每天都有一根柱（0 也显示，留出空档可读性）。
   *  One bar per day in the 7-day trend (zeros included, so gaps are readable). */
  it('渲染近 7 日趋势（7 根柱）', async () => {
    vi.mocked(api.getUploadStats).mockResolvedValue(STATS as any)
    const w = mount(ConsoleStats)
    await flushPromises()
    expect(w.findAll('.trend-bar')).toHaveLength(7)
    expect(w.findAll('.trend-bar').map((b) => (b.element as HTMLElement).title))
      .toEqual(STATS.days.map((d) => `${d.date}：${d.wake + d.transcribe + d['call-segment']} 次`))
  })

  /** 拉取失败：上传区块降级为 —，既有会话统计不受影响。
   *  Fetch failure: the upload section degrades to —, existing session stats unaffected. */
  it('统计接口失败时降级不炸', async () => {
    vi.mocked(api.getUploadStats).mockRejectedValue(new Error('network'))
    const w = mount(ConsoleStats)
    await flushPromises()
    expect(w.text()).toContain('消息总数')       // 原统计仍在。Original stats intact.
    expect(w.text()).toContain('上传合计')
    expect(w.find('.upload-stats').text()).toContain('—')
  })
})
