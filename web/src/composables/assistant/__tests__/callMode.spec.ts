import { describe, it, expect, vi, beforeEach } from 'vitest'

const stopListening = vi.fn()
const ensureListening = vi.fn()
// 桩复刻真实 startListening 的语义：成功即把 wakeEnabled 置 true、state 置 listening ——
// 电源开的真实落点依赖它（真实实现在 micControl.startListening）。
// wakeEnabled/state 走 **store 真身**：callMode 现在直接从 store 读（不再经门面转发），
// 本地桩会与真身脱钩导致断言测错对象。
// The stub mirrors real startListening: success sets wakeEnabled=true and state=listening.
// wakeEnabled/state come from the **real store**: callMode now reads them directly from the
// store (no facade forwarding), so a local stub would drift and assert the wrong object.
const startListening = vi.fn(async () => {
  wakeEnabled.value = true
  state.value = 'listening'
  return 'ok' as const
})

vi.mock('../wake/wakeOrchestrator', () => ({
  startListening, stopListening, ensureListening,
}))

// brief 原文是 '../../../../api'（web/api，不存在）—— 相对本测试文件应为三层到 src/api，
// 同目录 useWakeWord.spec.ts 亦用 '../../../api'。已就地更正。
vi.mock('../../../api', async (importOriginal) => {
  const orig = await importOriginal<typeof import('../../../api')>()
  return { ...orig, api: { ...orig.api, callStart: vi.fn(async () => ({ ok: true, open_window_s: 8, call_id: 'srv' })), callStop: vi.fn(async () => ({ ok: true })) } }
})

import { callActive, callConfig, callId, callWindowUntil, state, wakeEnabled } from '../store'

/**
 * 2026-10-11 状态图重定义：双击 = **语音电源**（关 ⇄ 静待），唤醒词 = 唤醒点
 * （静待 → 通话聆听中）。没有两个模式 —— 电源开直接落静待，漏斗由
 * enterCallFromWake 在唤醒时打开。
 *
 * 2026-10-11 state-diagram redefinition: double-click is the voice POWER (off ⇄ standby),
 * the wake word is the WAKE POINT (standby → call listening). There are no two modes —
 * power-on lands in standby, and the funnel opens via enterCallFromWake on wake.
 */
describe('语音电源开关（双击）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    callActive.value = false
    callId.value = ''
    callWindowUntil.value = 0
    wakeEnabled.value = false
    state.value = 'idle'
  })

  it('关闭态双击 → 电源开：取流并落静待（不开漏斗）', async () => {
    const { togglePower } = await import('../callMode')
    const { api } = await import('../../../api')
    await togglePower()
    expect(startListening).toHaveBeenCalled()
    expect(state.value).toBe('standby')          // 开机即唤醒前
    expect(callActive.value).toBe(false)         // 不进通话漏斗
    expect(vi.mocked(api.callStart)).not.toHaveBeenCalled()
  })

  it('静待双击 → 电源关：停麦回关闭态（不动通话会话）', async () => {
    const { togglePower } = await import('../callMode')
    const { api } = await import('../../../api')
    state.value = 'standby'
    wakeEnabled.value = true
    await togglePower()
    expect(stopListening).toHaveBeenCalled()
    expect(state.value).toBe('idle')
    expect(wakeEnabled.value).toBe(false)
    expect(vi.mocked(api.callStop)).not.toHaveBeenCalled()
  })

  it('通话聆听中双击 → 电源关：先关通话会话再回关闭态', async () => {
    const { togglePower } = await import('../callMode')
    const { api } = await import('../../../api')
    callActive.value = true
    callId.value = 'srv'
    state.value = 'listening'
    await togglePower()
    expect(callActive.value).toBe(false)
    expect(callId.value).toBe('')
    expect(vi.mocked(api.callStop)).toHaveBeenCalledWith({ call_id: 'srv' })
    expect(state.value).toBe('idle')
    expect(wakeEnabled.value).toBe(false)
  })
})

describe('静待 → 通话聆听中（enterCallFromWake）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    callActive.value = false
    callId.value = ''
    wakeEnabled.value = false
    state.value = 'standby'
  })

  it('成功：开漏斗会话、落 listening（文案=通话聆听中）、唤醒生命周期恢复', async () => {
    const { api } = await import('../../../api')
    const { enterCallFromWake } = await import('../callMode')
    const ok = await enterCallFromWake()
    expect(ok).toBe(true)
    expect(callActive.value).toBe(true)
    expect(callId.value).toBe('srv')             // 采用后端回显的会话 id
    expect(vi.mocked(api.callStart)).toHaveBeenCalledWith({ call_id: expect.any(String) })
    expect(state.value).toBe('listening')
    expect(wakeEnabled.value).toBe(true)
    expect(ensureListening).toHaveBeenCalled()   // 兜底拉麦（幂等）
  })

  it('后端未就绪 → 返回 false（调用方回退指令窗，不丢唤醒）', async () => {
    const { api } = await import('../../../api')
    vi.mocked(api.callStart).mockResolvedValueOnce({ ok: false } as any)
    const { enterCallFromWake } = await import('../callMode')
    const ok = await enterCallFromWake()
    expect(ok).toBe(false)
    expect(callActive.value).toBe(false)
    expect(callId.value).toBe('')
    expect(state.value).toBe('standby')          // 原地不动
  })

  it('voice.call.enabled=false → 返回 false（漏斗未启用）', async () => {
    const { enterCallFromWake } = await import('../callMode')
    const prev = callConfig.enabled
    callConfig.enabled = false
    try {
      expect(await enterCallFromWake()).toBe(false)
    } finally {
      callConfig.enabled = prev
    }
  })
})

describe('通话辅助状态', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    callActive.value = false
    callWindowUntil.value = 0
  })

  it('开放窗口计时', async () => {
    const { markTurnEnded, inOpenWindow } = await import('../store')
    expect(inOpenWindow()).toBe(false)
    markTurnEnded()
    expect(inOpenWindow()).toBe(true)
    callWindowUntil.value = Date.now() - 1
    expect(inOpenWindow()).toBe(false)
    expect(callConfig.open_window_s).toBe(8)
  })

  it('通话态播报期强制 barge-in（不依赖 vad.barge_in 配置）', async () => {
    const { callBargeInEnabled } = await import('../store')
    expect(callBargeInEnabled(false, true)).toBe(true)    // 配置关、通话开 → 仍启用
    expect(callBargeInEnabled(true, false)).toBe(true)    // 配置开、通话关 → 照配置
    expect(callBargeInEnabled(false, false)).toBe(false)  // 双关 → 不启用（非通话态零变化）
  })

  it('播报结束开窗（markTurnEnded 后 inOpenWindow=true）', async () => {
    const { markTurnEnded, inOpenWindow, callWindowUntil } = await import('../store')
    callWindowUntil.value = 0
    expect(inOpenWindow()).toBe(false)
    markTurnEnded()
    expect(inOpenWindow()).toBe(true)
  })
})
