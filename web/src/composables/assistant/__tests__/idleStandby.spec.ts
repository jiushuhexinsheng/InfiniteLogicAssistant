/**
 * 聆听空闲超时 → 静待（standby）。
 *
 * 口径（与用户确认）：只有实质输入续命；裸唤醒往返指令窗不续命；listen_idle_s=0 永不超时；
 * 静待不关麦（wakeEnabled 保持，由 segmentFlow 的唤醒判定放行 standby）。
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { nextTick } from 'vue'

async function setup(listenIdleS = 10) {
  vi.resetModules()
  const store = await import('../store')
  const orch = await import('../wake/orchState')
  const { registerWatches } = await import('../wake/watches')
  store.vadConfig.listen_idle_s = listenIdleS
  registerWatches()
  return { store, orch }
}

/** 推进状态并等 Vue watch 回调落盘（默认 pre-flush 是微任务）。 */
async function setState(s: { value: string }, v: string) {
  s.value = v
  await nextTick()
}

describe('聆听空闲超时 → 静待', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('进入聆听 10s 无实质输入 → 静待（wakeEnabled 保持，麦不关）', async () => {
    const { store } = await setup()
    store.wakeEnabled.value = true
    await setState(store.state, 'listening')
    vi.advanceTimersByTime(9_999)
    expect(store.state.value).toBe('listening')
    vi.advanceTimersByTime(1)
    expect(store.state.value).toBe('standby')
    expect(store.wakeEnabled.value).toBe(true)   // 静待只改 state，不关唤醒/不放麦
  })

  it('listen_idle_s=0 → 永不超时', async () => {
    const { store } = await setup(0)
    await setState(store.state, 'listening')
    vi.advanceTimersByTime(3_600_000)
    expect(store.state.value).toBe('listening')
  })

  it('resetIdleDeadline（实质输入）把截止时间往后推', async () => {
    const { store, orch } = await setup()
    await setState(store.state, 'listening')
    vi.advanceTimersByTime(8_000)
    orch.resetIdleDeadline()          // t=8，新截止 t=18
    vi.advanceTimersByTime(9_000)     // t=17 < 18
    expect(store.state.value).toBe('listening')
    vi.advanceTimersByTime(1_000)     // t=18
    expect(store.state.value).toBe('standby')
  })

  it('裸唤醒往返指令窗不续命（按剩余时间重挂）', async () => {
    const { store } = await setup()
    await setState(store.state, 'listening')
    vi.advanceTimersByTime(8_000)
    await setState(store.state, 'recording')   // 唤醒命中进指令窗
    await setState(store.state, 'listening')   // 指令窗超时回落
    vi.advanceTimersByTime(2_000)              // 总 10s，截止未被顺延
    expect(store.state.value).toBe('standby')
  })

  it('回合 done 重新起算 3 分钟', async () => {
    const { store } = await setup()
    await setState(store.state, 'listening')
    vi.advanceTimersByTime(8_000)
    await setState(store.state, 'done')        // t=8，done → resetIdleDeadline（截止 18）
    await setState(store.state, 'listening')
    vi.advanceTimersByTime(9_000)              // t=17 < 18
    expect(store.state.value).toBe('listening')
    vi.advanceTimersByTime(1_000)
    expect(store.state.value).toBe('standby')
  })

  it('离开聆听态（如 thinking）摘表，不误触发', async () => {
    const { store, orch } = await setup()
    await setState(store.state, 'listening')
    expect(orch.st.idleTimer).not.toBeNull()
    await setState(store.state, 'thinking')
    expect(orch.st.idleTimer).toBeNull()
    vi.advanceTimersByTime(3_600_000)
    expect(store.state.value).toBe('thinking')   // 陈旧触发被守卫拦住
  })
})
