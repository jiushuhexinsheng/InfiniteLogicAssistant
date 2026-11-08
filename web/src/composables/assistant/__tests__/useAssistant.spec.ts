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
    expect(callConfig.relax_after_misses).toBe(2)
  })
})

/** 设置页保存后的运行时热同步（docs/designs/10 4.2）。Settings-save runtime hot sync. */
describe('useAssistant.applyServerConfig 运行时热同步', () => {
  beforeEach(() => { vi.resetModules() })

  /** 唤醒词整体替换：旧词不得留下（否则保存后仍能被旧词唤醒）。 */
  it('唤醒词整体替换，旧词不残留', async () => {
    const { useAssistant } = await import('../../useAssistant')
    const asst = useAssistant()
    asst.applyServerConfig({ wake: { keywords: ['衍衡', '洛吉斯'] } })
    expect(asst.wakeKeywords.value).toEqual(['衍衡', '洛吉斯'])
    asst.applyServerConfig({ wake: { keywords: ['新名字'] } })
    expect(asst.wakeKeywords.value).toEqual(['新名字'])
  })

  /** 下发的空唤醒词列表回退到内置默认，而不是把界面提示清成空。 */
  it('空唤醒词回退到内置默认', async () => {
    const { useAssistant } = await import('../../useAssistant')
    const asst = useAssistant()
    asst.applyServerConfig({ wake: { keywords: [] } })
    expect(asst.wakeKeywords.value).toEqual(['衍衡', '洛吉斯'])
  })

  /** 二次应用时先重置默认再合并：被删掉的键必须回到默认值，而不是停留在上一次的下发值。 */
  it('二次应用先重置默认，被删除的键还原', async () => {
    const { useAssistant } = await import('../../useAssistant')
    const { vadConfig, callConfig, hardwareConfig } = await import('../store')
    const asst = useAssistant()
    asst.applyServerConfig({
      vad: { followup_window_ms: 9000 },
      call: { open_window_s: 3 },
      hardware: { input_device: 'mic-2' },
      streaming: false,
    })
    expect(vadConfig.followup_window_ms).toBe(9000)
    expect(callConfig.open_window_s).toBe(3)
    expect(hardwareConfig.input_device).toBe('mic-2')
    expect(asst.streamingEnabled.value).toBe(false)

    // 新配置删掉了这些键 → 回到默认值。
    asst.applyServerConfig({})
    expect(vadConfig.followup_window_ms).toBe(6000)
    expect(callConfig.open_window_s).toBe(8)
    expect(hardwareConfig.input_device).toBe('')
    expect(asst.streamingEnabled.value).toBe(true)
  })
})

/** 清空对话必须连后端会话一起结束（docs/designs/10 4.4）。 */
describe('useAssistant.clearMessages 重置后端会话', () => {
  beforeEach(() => { vi.resetModules() })

  it('先带着旧 sessionId 调 stopTask，再清本地会话/待答/token', async () => {
    const { useAssistant } = await import('../../useAssistant')
    const store = await import('../store')
    const { api } = await import('../../../api')
    const asst = useAssistant()
    asst.currentSessionId.value = 's-1'
    store.pendingQuestion.value = { text: '选哪个？', kind: 'text', options: [] }
    store.tokenUsage.value = { total_tokens: 9 } as any
    store.addMessage('user', 'hi')

    asst.clearMessages()

    // stopTask 必须拿到**清空前的** sessionId，否则后端任务无人停。
    expect(api.stopTask).toHaveBeenCalledWith('s-1')
    expect(asst.currentSessionId.value).toBe('')
    expect(asst.pendingQuestion.value).toBeNull()
    expect(asst.tokenUsage.value).toEqual({})
    expect(asst.messages.value).toEqual([])
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
