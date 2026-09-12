// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

// 只桩网络层，保留组件真实逻辑。Stub only the network layer, keeping the component's real logic.
vi.mock('../../../api', () => ({ api: { getTools: vi.fn() } }))

import { api } from '../../../api'
import ConsoleTools from '../ConsoleTools.vue'

/** 工具列表加载的成功/失败展示（错误处理统一化后的回归网）。
 *  Tool list loading, success and failure (regression net for the unified error handling). */
describe('ConsoleTools 加载状态', () => {
  beforeEach(() => {
    vi.mocked(api.getTools).mockReset()
  })

  /** 成功：渲染工具名，且不显示错误提示。Success: renders tool names and no error note. */
  it('加载成功渲染工具列表', async () => {
    vi.mocked(api.getTools).mockResolvedValue({
      ok: true,
      tools: [{ function: { name: 'read_file', description: '读取文件', parameters: {} } }],
    } as any)
    const w = mount(ConsoleTools)
    await flushPromises()
    expect(w.text()).toContain('read_file')
    expect(w.find('.ui-errnote').exists()).toBe(false)
  })

  /** 业务失败（ok=false）：走 UiErrorNote，而不是静默。Business failure: surfaces via UiErrorNote instead of silently. */
  it('业务失败展示统一错误提示', async () => {
    vi.mocked(api.getTools).mockResolvedValue({ ok: false, error: '后端未就绪' } as any)
    const w = mount(ConsoleTools)
    await flushPromises()
    expect(w.find('.ui-errnote').text()).toBe('后端未就绪')
  })

  /** 请求抛错：同样可见（原先只写 console）。A thrown request error is visible too (previously console-only). */
  it('请求抛错时展示错误文案', async () => {
    vi.mocked(api.getTools).mockRejectedValue(new Error('连接被拒绝'))
    const w = mount(ConsoleTools)
    await flushPromises()
    expect(w.find('.ui-errnote').text()).toBe('连接被拒绝')
  })
})
