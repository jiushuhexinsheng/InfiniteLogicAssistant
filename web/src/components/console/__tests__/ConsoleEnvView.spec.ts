// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

vi.mock('../../../api', () => ({ api: { getEnv: vi.fn() } }))

import { api } from '../../../api'
import ConsoleEnvView from '../ConsoleEnvView.vue'

/** 环境快照加载的错误处理。Error handling for environment snapshot loading. */
describe('ConsoleEnvView', () => {
  beforeEach(() => { vi.mocked(api.getEnv).mockReset() })

  /** 成功：内容渲染进 <pre>。Success: content renders inside <pre>. */
  it('加载成功渲染环境快照', async () => {
    vi.mocked(api.getEnv).mockResolvedValue({ ok: true, content: 'OS: Windows 11' } as any)
    const w = mount(ConsoleEnvView)
    await flushPromises()
    expect(w.find('.env-pre').text()).toBe('OS: Windows 11')
  })

  /** 关键回归：失败不再拼进 content 渲染到 <pre>，而是走统一错误提示。
   *  Key regression: failures no longer get baked into content inside <pre>, but surface via the error note. */
  it('加载失败走错误提示，不混入内容区', async () => {
    vi.mocked(api.getEnv).mockRejectedValue(new Error('连接被拒绝'))
    const w = mount(ConsoleEnvView)
    await flushPromises()
    expect(w.find('.ui-errnote').text()).toBe('连接被拒绝')
    expect(w.find('.env-pre').exists()).toBe(false)
  })
})
