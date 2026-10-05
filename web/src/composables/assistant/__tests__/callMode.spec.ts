import { describe, it, expect, vi, beforeEach } from 'vitest'

const startListening = vi.fn(async () => 'ok' as const)
const stopListening = vi.fn()
const toggleWake = vi.fn(async () => {})
const wakeEnabled = { value: false }

vi.mock('../wake/wakeOrchestrator', () => ({
  startListening, stopListening, toggleWake,
  get wakeEnabled() { return wakeEnabled },
}))

// brief 原文是 '../../../../api'（web/api，不存在）—— 相对本测试文件应为三层到 src/api，
// 同目录 useWakeWord.spec.ts 亦用 '../../../api'。已就地更正。
vi.mock('../../../api', async (importOriginal) => {
  const orig = await importOriginal<typeof import('../../../api')>()
  return { ...orig, api: { ...orig.api, callStart: vi.fn(async () => ({ ok: true, open_window_s: 8 })), callStop: vi.fn(async () => ({ ok: true })) } }
})

import { callActive, callConfig, callWindowUntil } from '../store'

describe('通话 FSM', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    callActive.value = false
    callWindowUntil.value = 0
    wakeEnabled.value = false
  })

  it('进入通话：先停唤醒再建会话再启动监听', async () => {
    const { toggleCall } = await import('../callMode')
    wakeEnabled.value = true          // 唤醒正在听 → 必须先停（Review Focus #3）
    await toggleCall()
    expect(toggleWake).toHaveBeenCalled()
    expect(callActive.value).toBe(true)
    expect(startListening).toHaveBeenCalled()
  })

  it('退出通话：清标志、停监听、关会话', async () => {
    const { toggleCall } = await import('../callMode')
    callActive.value = true
    await toggleCall()
    expect(callActive.value).toBe(false)
    expect(stopListening).toHaveBeenCalled()
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
    // 归属：Task 10 把 markTurnEnded/inOpenWindow 放在 store（避免 wakeOrchestrator↔callMode 循环导入）。
    const { markTurnEnded, inOpenWindow, callWindowUntil } = await import('../store')
    callWindowUntil.value = 0
    expect(inOpenWindow()).toBe(false)
    markTurnEnded()
    expect(inOpenWindow()).toBe(true)
  })
})
