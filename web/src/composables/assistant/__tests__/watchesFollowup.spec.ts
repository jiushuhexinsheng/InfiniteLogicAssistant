// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'

/** 麦克风链路在 jsdom 里不可用：watches 只关心状态迁移，取流一律桩掉。
 *  The mic path is unavailable under jsdom; watches only exercises state transitions. */
vi.mock('../wake/micControl', () => ({
  ensureListening: vi.fn(async () => true),
  stopListening: vi.fn(),
}))

/**
 * 长 TTS 不得吃掉续聊窗（docs/designs/10 4.5）。
 *
 * 续聊窗原本从 `done` 事件（≈播报开始）起算；长播报期间窗口先到期 → 回 listening，
 * 播报结束时旧代码只在 state 仍为 followup 时重挂定时器，于是这个窗口**永远丢了**。
 * 修复：播报结束若回合已完成（listening/standby），重新开窗并计时。
 *
 * Long TTS must not eat the follow-up window (docs/designs/10 4.5). The window used to
 * start at the `done` event (≈ playback start), so a long reply expired it mid-speech
 * and the old code only re-armed when the state was still `followup` — the window was
 * lost for good. Fix: at end of playback, re-open it when the turn is already complete.
 */
describe('watches：播报结束重开续聊窗', () => {
  afterEach(() => { vi.useRealTimers() })

  it('长播报期间窗口已到期 → 播报结束时重新进入 followup', async () => {
    vi.useFakeTimers()
    const { ref, nextTick } = await import('vue')
    const { st } = await import('../wake/orchState')
    const { registerWatches } = await import('../wake/watches')
    const { state, wakeEnabled, vadConfig } = await import('../store')

    vadConfig.followup_window_ms = 6000
    st.deps = {
      api: {} as never,
      sendText: vi.fn(),
      sendAnswer: vi.fn(),
      speaking: ref(false),
    }
    registerWatches()

    // 回合早已完成 → 窗口到期后已回 listening；此时 TTS 还在播。
    state.value = 'listening'
    wakeEnabled.value = true
    st.deps.speaking.value = true
    await nextTick()
    st.deps.speaking.value = false
    await nextTick()

    expect(state.value).toBe('followup')
  })
})
