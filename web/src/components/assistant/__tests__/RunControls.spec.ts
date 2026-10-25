// @vitest-environment jsdom
/** 回合控制条：暂停/继续 + 停止。Run controls: pause/resume + stop. */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('../../../api', () => ({
  api: { pauseTask: vi.fn(), resumeTask: vi.fn(), stopTask: vi.fn() },
  streamUtter: vi.fn(),
}))
// 停止要经 abortChat（断流 + stopTask），整个 useChat 模块桩掉更稳。
vi.mock('../../../composables/assistant/useChat', () => ({
  abortChat: vi.fn(),
}))

import { api } from '../../../api'
import { abortChat } from '../../../composables/assistant/useChat'
import { currentSessionId, state } from '../../../composables/assistant/store'
import { paused, resetPause } from '../../../composables/assistant/useChatPause'
import RunControls from '../RunControls.vue'

describe('RunControls', () => {
  beforeEach(() => {
    resetPause()
    state.value = 'responding'
    currentSessionId.value = 's1'
    vi.mocked(api.pauseTask).mockReset().mockResolvedValue({ ok: true } as any)
    vi.mocked(api.resumeTask).mockReset().mockResolvedValue({ ok: true } as any)
    vi.mocked(abortChat).mockReset()
  })

  it('回合进行中渲染暂停与停止两个按钮', () => {
    const w = mount(RunControls)
    expect(w.find('[data-run="pause"]').exists()).toBe(true)
    expect(w.find('[data-run="stop"]').exists()).toBe(true)
  })

  it('空闲时不渲染（不占位）', () => {
    state.value = 'idle'
    const w = mount(RunControls)
    expect(w.find('[data-run="pause"]').exists()).toBe(false)
  })

  it('点暂停 → 调后端 pause（stop 档）并把按钮切成继续', async () => {
    const w = mount(RunControls)
    await w.find('[data-run="pause"]').trigger('click')
    await vi.waitFor(() => expect(paused.value).toBe(true))
    expect(api.pauseTask).toHaveBeenCalledWith('s1', 'stop')
    expect(w.find('[data-run="pause"]').attributes('aria-label')).toBe('继续')
  })

  it('暂停态点继续 → 调 resume', async () => {
    const w = mount(RunControls)
    await w.find('[data-run="pause"]').trigger('click')
    await vi.waitFor(() => expect(paused.value).toBe(true))
    await w.find('[data-run="pause"]').trigger('click')
    await vi.waitFor(() => expect(paused.value).toBe(false))
    expect(api.resumeTask).toHaveBeenCalledWith('s1')
  })

  it('点停止 → abortChat（断流 + stopTask），并清暂停标志', async () => {
    const w = mount(RunControls)
    paused.value = true
    await w.find('[data-run="stop"]').trigger('click')
    expect(abortChat).toHaveBeenCalled()
    expect(paused.value).toBe(false)
  })
})
