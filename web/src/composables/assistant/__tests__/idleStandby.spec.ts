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

  /**
   * 静止超时**无条件**生效（用户口径：静止 3 分钟 → 静待，通话中也一样）：
   * 到点自动干净退出通话（callActive=false、漏斗停、麦保持、唤醒生命周期恢复）再落静待。
   * The idle timeout applies **unconditionally** (user rule: silent 3 min → standby, mid-call
   * too): on expiry the call is exited cleanly (funnel stops, mic stays, the wake lifecycle
   * is restored) before standby is entered.
   */
  it('通话中静止超时 → 自动退通话并进静待', async () => {
    const { store, orch } = await setup()
    store.callActive.value = true
    store.wakeEnabled.value = false        // 进通话时互斥关掉的唤醒
    await setState(store.state, 'listening')
    expect(orch.st.idleTimer).not.toBeNull()          // 通话中照样武装
    vi.advanceTimersByTime(10_000)
    expect(store.state.value).toBe('standby')
    expect(store.callActive.value).toBe(false)        // 通话已干净退出
    expect(store.wakeEnabled.value).toBe(true)        // 唤醒生命周期恢复（可再唤醒）
  })
})

/**
 * 静待中的再唤醒（用户报告：进入静待后无法被重新唤醒）：超时进 standby →
 * handleSegment 走 KWS 快检命中 → 必须进指令窗（recording + 提示音路径）。
 * 端到端复用 useWakeWord.spec 的 mock 模式。
 */
describe('静待中重新唤醒', () => {
  beforeEach(() => { vi.resetModules(); vi.useFakeTimers(); localStorage.clear() })
  afterEach(() => { vi.useRealTimers() })

  async function standBy(checkResp: { ok: boolean; hit: boolean; bypass: boolean }
                         = { ok: true, hit: true, bypass: false }) {
    vi.doMock('../../../api', () => ({
      api: {
        wakeCheck: vi.fn(async () => checkResp),
        wakeDetect: vi.fn(async () => ({ ok: true, matched: true, command: '', text: '衍衡。' })),
        transcribe: vi.fn(async () => ({ ok: true, text: '' })),
      },
    }))
    vi.doMock('../useChat', () => ({ sendText: vi.fn(), sendAnswer: vi.fn(), runTurn: vi.fn() }))
    vi.doMock('../useTts', () => ({ speaking: { value: false }, speakAuto: vi.fn(), stopSpeak: vi.fn() }))
    const store = await import('../store')
    const orch = await import('../wake/orchState')
    const mod = await import('../useWakeWord')   // 导入即注入 DI + registerWatches
    store.vadConfig.listen_idle_s = 1
    store.wakeEnabled.value = true
    store.state.value = 'listening'
    await nextTick()
    vi.advanceTimersByTime(1_000)               // 空闲超时 → standby
    await nextTick()
    expect(store.state.value).toBe('standby')
    return { store, orch, mod }
  }

  it('静待中 KWS 快检命中 → 进指令窗（recording + 已唤醒提示）', async () => {
    const { store, mod } = await standBy()
    await mod.handleSegment(new Blob(['x']))
    await vi.advanceTimersByTimeAsync(0)         // 让 wakeCheck 等微任务 settle
    expect(store.state.value).toBe('recording')
    expect(store.statusLine.value).toContain('已唤醒')
  })

  it('静待中快检未命中 → 保持静待（不误动作）', async () => {
    const { store, mod } = await standBy({ ok: true, hit: false, bypass: false })
    await mod.handleSegment(new Blob(['x']))
    await vi.advanceTimersByTimeAsync(0)
    expect(store.state.value).toBe('standby')
  })
})
