import { describe, it, expect, vi, beforeEach } from 'vitest'

// 回归测试：vosk.js 内嵌 worker 只支持 URL 加载模型（load() 里 modelUrl.replace(...)，
// modelUrl 必须是字符串）。若前端预下载模型字节并把 ArrayBuffer 交给
// WakeWordEngine.init → vosk.createModel(ArrayBuffer) → worker 抛
// "modelUrl.replace is not a function"。
// 因此 initWakeModel 必须把 modelPath 字符串交给引擎，绝不传字节。
describe('useWakeWord 唤醒模型加载', () => {
  beforeEach(() => {
    vi.resetModules()
    // 引擎桩：记录 init 收到的参数
    ;(globalThis as any).WakeWordEngine = { init: vi.fn(async () => true) }
    // 修复后不应再预下载模型（无 fetch）；若代码回归到 fetch 路径会立刻失败
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('no network')))
  })

  it('initWakeModel 交给引擎的是 modelPath 字符串，而非预下载字节', async () => {
    const { initWakeModel } = await import('../useWakeWord')
    const ok = await initWakeModel()
    expect(ok).toBe(true)
    const init = (globalThis as any).WakeWordEngine.init
    expect(init).toHaveBeenCalledTimes(1)
    const arg = init.mock.calls[0][0]
    expect(arg.modelPath).toBe('/models/vosk-model-small-cn-0.22.tar.gz')
    expect(arg.model).toBeUndefined() // 绝不传字节（vosk worker 不支持 ArrayBuffer）
  })
})
