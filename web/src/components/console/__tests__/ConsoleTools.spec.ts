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

  /** 折叠触发器键盘可达：Enter / Space 都能开合，且带 `aria-expanded`。
   *  ⚠️ `data-compact` 那条断言是**几何护栏** —— 触发器是 div + role="button"，少了它就会命中
   *  app.css 的全局 44px 最小触达规则把行撑高。
   *  The trigger is keyboard reachable (Enter/Space) and carries aria-expanded. The `data-compact`
   *  assertion is a **geometry guard**: without it app.css's global 44px touch-target rule would
   *  grow the row. */
  it('折叠触发器 Enter / Space 可开合（键盘可达）', async () => {
    vi.mocked(api.getTools).mockResolvedValue({
      ok: true,
      tools: [{ function: { name: 'read_file', description: '读取文件', parameters: { path: 'x' } } }],
    } as any)
    const w = mount(ConsoleTools)
    await flushPromises()
    const head = w.find('.tool-head')
    expect(head.attributes('role')).toBe('button')
    expect(head.attributes('tabindex')).toBe('0')
    expect(head.attributes('data-compact')).toBeDefined()
    expect(head.attributes('aria-expanded')).toBe('false')
    await head.trigger('keydown', { key: 'Enter' })
    expect(head.attributes('aria-expanded')).toBe('true')
    expect(w.find('.tool-params').exists()).toBe(true)
    await head.trigger('keydown', { key: ' ' })
    expect(head.attributes('aria-expanded')).toBe('false')
    expect(w.find('.tool-params').exists()).toBe(false)
  })
})
