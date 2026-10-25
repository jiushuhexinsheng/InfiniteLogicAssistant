import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../../api', () => ({
  api: {
    pauseTask: vi.fn(),
    resumeTask: vi.fn(),
    stopTask: vi.fn(),
  },
  streamUtter: vi.fn(),
}))

import { api } from '../../../api'
import { currentSessionId, state } from '../store'
import { paused, pauseTurn, resetPause, resumeTurn, togglePause, turnActive } from '../useChatPause'

/**
 * 暂停/继续：与后端 PauseController 三档语义对齐（前端默认 safe stop ——
 * 「LLM 也暂停」即中断当前生成、恢复后续写）。
 * Pause/resume aligned with the backend PauseController modes (the frontend defaults
 * to safe stop: "pause the LLM too" aborts the current generation and resumes on
 * continue).
 */
describe('useChatPause', () => {
  beforeEach(() => {
    resetPause()
    currentSessionId.value = ''
    state.value = 'idle'
    vi.mocked(api.pauseTask).mockReset()
    vi.mocked(api.resumeTask).mockReset()
  })

  it('暂停把 safe stop 档发给后端', async () => {
    currentSessionId.value = 's1'
    state.value = 'responding'
    vi.mocked(api.pauseTask).mockResolvedValue({ ok: true } as any)

    await pauseTurn()

    expect(api.pauseTask).toHaveBeenCalledWith('s1', 'stop')
    expect(paused.value).toBe(true)
  })

  it('继续调用 resume 并清掉暂停标志', async () => {
    currentSessionId.value = 's1'
    state.value = 'responding'
    vi.mocked(api.pauseTask).mockResolvedValue({ ok: true } as any)
    vi.mocked(api.resumeTask).mockResolvedValue({ ok: true } as any)
    await pauseTurn()

    await resumeTurn()

    expect(api.resumeTask).toHaveBeenCalledWith('s1')
    expect(paused.value).toBe(false)
  })

  it('没有会话 id 时不发请求也不改状态', async () => {
    state.value = 'thinking'

    await pauseTurn()

    expect(api.pauseTask).not.toHaveBeenCalled()
    expect(paused.value).toBe(false)
  })

  it('后端拒绝时回退暂停标志（不留假的已暂停）', async () => {
    currentSessionId.value = 's1'
    vi.mocked(api.pauseTask).mockRejectedValue(new Error('404'))

    await pauseTurn()

    expect(paused.value).toBe(false)
  })

  it('togglePause 在暂停与继续之间切换', async () => {
    currentSessionId.value = 's1'
    vi.mocked(api.pauseTask).mockResolvedValue({ ok: true } as any)
    vi.mocked(api.resumeTask).mockResolvedValue({ ok: true } as any)

    await togglePause()
    expect(paused.value).toBe(true)
    await togglePause()
    expect(paused.value).toBe(false)
  })

  it('turnActive 覆盖 running 状态与暂停态', () => {
    state.value = 'responding'
    expect(turnActive.value).toBe(true)
    state.value = 'done'
    expect(turnActive.value).toBe(false)
    state.value = 'idle'
    paused.value = true   // 暂停时状态可能已落回基线，仍视为回合在跑
    expect(turnActive.value).toBe(true)
  })

  it('resetPause 只清本地标志，不向后端发恢复请求', () => {
    paused.value = true
    resetPause()
    expect(paused.value).toBe(false)
    expect(api.resumeTask).not.toHaveBeenCalled()
  })
})
