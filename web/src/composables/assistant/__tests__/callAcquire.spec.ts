/**
 * acquireAndStart 选路（终审 Important #1）：webspeech 模式 + 通话态必须走 segmenter 路径。
 *
 * 缝隙说明：deps 注入够不到 mode 选择 —— acquireAndStart 只读 store 的 wakeMode/callActive，
 * 所以建最小假件：桩掉 segmenter 构造 + 麦克风取流，只留「选了哪条路」可观测。
 * webspeech 分支在 node 测试环境必然失败（无 SpeechRecognition → isAvailable()=false），
 * 这本身就成了 webspeech 路被选中的确定性指纹。
 *
 * Acquire routing (final-review Important #1): webspeech mode + call-active must take the
 * segmenter path. deps injection does not reach the mode choice (acquireAndStart reads only
 * store wakeMode/callActive), so this file builds the minimal double: stub segmenter
 * construction + mic acquisition so "which path was chosen" is observable. The webspeech
 * branch necessarily fails in the node test env (no SpeechRecognition → isAvailable()=false),
 * which is itself the deterministic fingerprint that the webspeech path was selected.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const fx = vi.hoisted(() => {
  const recorders: Array<{ start: ReturnType<typeof vi.fn>; stop: ReturnType<typeof vi.fn> }> = []
  return {
    recorders,
    getUserMedia: vi.fn(async () => ({ getTracks: () => [{ stop: vi.fn() }] })),
    enumerateDevices: vi.fn(async () => [{ kind: 'audioinput', label: 'fake-mic' }]),
  }
})

vi.mock('../useSegmentRecorder', () => ({
  createSegmentRecorder: () => {
    const h = { start: vi.fn(), stop: vi.fn(), isRecording: () => false }
    fx.recorders.push(h)
    return h
  },
}))

describe('webspeech 模式下的 acquire 选路（通话漏斗可达性）', () => {
  beforeEach(() => {
    vi.resetModules()
    fx.recorders.length = 0
    fx.getUserMedia.mockClear()
    fx.enumerateDevices.mockClear()
    vi.stubGlobal('navigator', {
      mediaDevices: { enumerateDevices: fx.enumerateDevices, getUserMedia: fx.getUserMedia },
    })
  })

  /** webspeech 模式下走 startListening（acquireAndStart 的公开入口），返回结局与 store。 */
  async function startWith(callActive: boolean) {
    const store = await import('../store')
    store.wakeMode.value = 'webspeech'   // 直接置 ref：不走 setWakeMode，免得持久化串到下一用例
    store.callActive.value = callActive
    const ww = await import('../wake/wakeOrchestrator')
    const outcome = await ww.startListening()
    return { outcome, store }
  }

  it('webspeech + 通话态 → 走 segmenter 取流（漏斗可达，不进 webspeech 分支）', async () => {
    const { outcome, store } = await startWith(true)

    expect(outcome).toBe('ok')
    expect(fx.getUserMedia).toHaveBeenCalledTimes(1)   // segmenter 路的取流
    expect(fx.recorders).toHaveLength(1)               // segmenter 已构造并启动
    expect(fx.recorders[0].start).toHaveBeenCalledTimes(1)
    // webspeech 分支的独有失败提示出现即说明选错了路（node 无 SpeechRecognition 必现）
    expect(store.statusLine.value).not.toContain('Web Speech API')
  })

  it('webspeech + 非通话态 → 仍走 webspeech 分支（退出通话自然回落）', async () => {
    const { outcome, store } = await startWith(false)

    // startListening 失败时回传的是 statusLine 文案（非 'mic-error' 枚举）——
    // 「不支持 Web Speech API」是 webspeech 分支在 node 环境的确定性指纹。
    expect(outcome).toContain('不支持 Web Speech API')
    expect(store.statusLine.value).toContain('不支持 Web Speech API')  // 指纹：确实选了 webspeech 路
    expect(fx.getUserMedia).not.toHaveBeenCalled()               // 未走 segmenter 路
    expect(fx.recorders).toHaveLength(0)
  })
})
