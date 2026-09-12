import { describe, it, expect, vi, beforeEach } from 'vitest'

/** 回归测试：vosk.js 内嵌 worker 只支持 URL 加载模型（load() 里 modelUrl.replace(...)，
 *  modelUrl 必须是字符串）。若前端预下载模型字节并把 ArrayBuffer 交给
 *  WakeWordEngine.init → vosk.createModel(ArrayBuffer) → worker 抛
 *  "modelUrl.replace is not a function"。
 *  因此 initWakeModel 必须把 modelPath 字符串交给引擎，绝不传字节。
 *  Regression test: vosk.js embedded worker only supports URL-based model loading (modelUrl.replace(...) in load(),
 *  modelUrl must be string). If frontend pre-downloads model bytes and passes ArrayBuffer to
 *  WakeWordEngine.init → vosk.createModel(ArrayBuffer) → worker throws
 *  "modelUrl.replace is not a function".
 *  Therefore initWakeModel must pass modelPath string to engine, never bytes. */
describe('useWakeWord 唤醒模型加载', () => {
  /** 每个测试前重置模块和模拟。Reset modules and mocks before each test. */
  beforeEach(() => {
    vi.resetModules()
    // 引擎桩：记录 init 收到的参数。Engine stub: record init parameters.
    ;(globalThis as any).WakeWordEngine = { init: vi.fn(async () => true) }
    // 修复后不应再预下载模型（无 fetch）；若代码回归到 fetch 路径会立刻失败。
    // After fix, no pre-download model (no fetch); if code regresses to fetch path, it will fail immediately.
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('no network')))
  })

  /** 测试 initWakeModel 交给引擎的是 modelPath 字符串，而非预下载字节。
   *  Test initWakeModel passes modelPath string to engine, not pre-downloaded bytes. */
  it('initWakeModel 交给引擎的是 modelPath 字符串，而非预下载字节', async () => {
    const { initWakeModel } = await import('../useWakeWord')
    const ok = await initWakeModel()
    expect(ok).toBe(true)
    const init = (globalThis as any).WakeWordEngine.init
    expect(init).toHaveBeenCalledTimes(1)
    const arg = init.mock.calls[0][0]
    expect(arg.modelPath).toBe('/models/vosk-model-small-cn-0.22.tar.gz')
    expect(arg.model).toBeUndefined() // 绝不传字节（vosk worker 不支持 ArrayBuffer）。Never pass bytes (vosk worker doesn't support ArrayBuffer).
  })
})

/** 麦克风错误文案：统一走 formatError，但必须保留 e.name 兜底链（否则未知错误名会丢信息）。
 *  Microphone error text: unified through formatError, but the e.name fallback chain must be
 *  preserved (otherwise an unrecognized error name loses information). */
describe('describeMicError 麦克风错误文案', () => {
  /** 已知错误名走专用提示（不受本次统一化影响）。Known error names keep their dedicated hints. */
  it('已知错误名走专用提示', async () => {
    const { describeMicError } = await import('../useWakeWord')
    expect(describeMicError({ name: 'NotAllowedError' })).toContain('权限被拒绝')
  })

  /** 未知错误名但有 message：用 message，标点为全角。 */
  it('有 message 时使用 message 且标点为全角', async () => {
    const { describeMicError } = await import('../useWakeWord')
    expect(describeMicError(new Error('设备忙'))).toBe('麦克风访问失败：设备忙')
  })

  /** 无 message 但有 name：回退到 name —— 这是 formatError 不覆盖的兜底链。 */
  it('无 message 时回退到错误名，不丢 e.name', async () => {
    const { describeMicError } = await import('../useWakeWord')
    expect(describeMicError({ name: 'WeirdError' })).toBe('麦克风访问失败：WeirdError')
  })

  /** 既无 message 也无 name：给出「未知错误」。 */
  it('既无 message 也无 name 时给出未知错误', async () => {
    const { describeMicError } = await import('../useWakeWord')
    expect(describeMicError({})).toBe('麦克风访问失败：未知错误')
  })
})
