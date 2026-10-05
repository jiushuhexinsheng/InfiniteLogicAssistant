import { beforeEach, describe, expect, it, vi } from 'vitest'

// 只桩掉网络与浏览器语音层：useAssistant 经 useChat/useWakeWord 拉入这两层。
// Stub only the network and browser-speech layers: useAssistant pulls both in via useChat/useWakeWord.
vi.mock('../../../api', () => ({
  api: { answer: vi.fn(), callTool: vi.fn(), forkSession: vi.fn(), stopTask: vi.fn() },
  streamUtter: vi.fn(),
}))
vi.mock('../useTts', async () => {
  const { ref } = await import('vue')
  return { speakAuto: vi.fn(), stopSpeak: vi.fn(), speaking: ref(false) }
})

/** useAssistant.init 配置透传（Task 1：/api/config 的 call 段必须能覆盖前端默认值）。
 *  useAssistant.init config passthrough (Task 1: the `call` block of /api/config must be able
 *  to override the frontend defaults). */
describe('useAssistant init 透传配置', () => {
  // init 有模块级 initialized 幂等闸：每个用例拿到全新模块实例（含全新 callConfig）。
  // init has a module-level `initialized` idempotence gate: each case gets a fresh module
  // registry (and therefore a fresh callConfig).
  beforeEach(() => { vi.resetModules() })

  /** `init({ call })` 把 /api/config 的 call 段合并进 callConfig（钉住 Task 1 的 call 分支）。
   *  `init({ call })` merges the `call` block of /api/config into callConfig (pins the Task 1
   *  call branch). */
  it('init({ call }) 用下发的 call 段覆盖 callConfig 默认值', async () => {
    const { useAssistant } = await import('../../useAssistant')
    const { callConfig } = await import('../store')
    // 初始为内置默认（8s 开放窗口）。Built-in default first (8s open window).
    expect(callConfig.open_window_s).toBe(8)
    useAssistant().init({ call: { open_window_s: 5 } })
    expect(callConfig.open_window_s).toBe(5)
    // 未下发的字段保持默认（只覆盖给了的键）。Undeclared fields keep their defaults
    // (only the keys actually sent are overwritten).
    expect(callConfig.enabled).toBe(true)
    expect(callConfig.l0_min_rms).toBe(0.02)
  })

  /** 无 call 段时不动 callConfig（init 是可选配置，不传=纯默认）。
   *  Without a `call` block, callConfig is untouched (init takes optional config; omitting it
   *  leaves the built-in defaults). */
  it('init 不带 call 段时保留内置默认', async () => {
    const { useAssistant } = await import('../../useAssistant')
    const { callConfig } = await import('../store')
    useAssistant().init()
    expect(callConfig.open_window_s).toBe(8)
    expect(callConfig.smart_turn_enabled).toBe(true)
  })
})

/** Task 11 接线：双击悬浮球改走通话开关 —— useAssistant 必须把 toggleCall 暴露给
 *  FloatingAssistant（与 toggleWake 同模式；徽章仍走 toggleWake = R7）。
 *  Task 11 wiring: the double-click now toggles call — useAssistant must expose toggleCall
 *  to FloatingAssistant (same pattern as toggleWake; the badge keeps toggleWake = R7). */
describe('useAssistant 通话入口接线', () => {
  beforeEach(() => { vi.resetModules() })

  it('返回对象暴露 toggleCall（双击悬浮球入口）', async () => {
    const { useAssistant } = await import('../../useAssistant')
    expect(typeof useAssistant().toggleCall).toBe('function')
  })

  it('唤醒入口仍在：toggleWake 照常暴露（R7 徽章接线不动）', async () => {
    const { useAssistant } = await import('../../useAssistant')
    expect(typeof useAssistant().toggleWake).toBe('function')
  })
})
