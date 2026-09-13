import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick } from 'vue'

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

/**
 * 提问待答时的转写必须走答案通道，而不是开新一轮 —— 这是「一说话就把当前提问搞挂」的根因修复。
 * 断言可观测效果（api.answer 被调用 / messages 未变），而非 spy 内部函数。
 *
 * A transcript while a question is pending must go to the answer channel, not start a new
 * turn — the fix for "speaking hangs the pending question". Assertions are on observable
 * effects (api.answer called / messages unchanged) rather than on internal spies.
 */
describe('useWakeWord handleTranscript 分流', () => {
  beforeEach(() => {
    vi.resetModules()
    ;(globalThis as any).WakeWordEngine = { init: vi.fn(async () => true) }
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('no network')))
  })

  async function setup(transcript: string, opts?: { pending?: boolean; match?: boolean }) {
    const apiMod = await import('../../../api')
    const store = await import('../store')
    vi.spyOn(apiMod.api, 'transcribe').mockResolvedValue({ ok: true, text: transcript } as any)
    const answerSpy = vi.spyOn(apiMod.api, 'answer').mockResolvedValue({ ok: true } as any)
    store.currentSessionId.value = 's1'
    store.messages.value = []
    store.pendingQuestion.value = (opts?.pending ?? true)
      ? {
          text: '确认执行吗？', kind: 'choice',
          options: opts?.match === false
            ? [{ value: 'yes', label: '允许本次' }]
            : [{ value: 'yes', label: '允许本次' }, { value: 'no', label: '拒绝' }],
        }
      : null
    return { apiMod, store, answerSpy }
  }

  /** 命中选择 → 回传对应 value，不开新一轮。
   *  记录里应是**回答记录**（用 option 的 label），而非 turn 路径写入的原始消息。 */
  it('命中选项时回传 choice 且不开新一轮', async () => {
    const { store, answerSpy } = await setup('允许本次')
    const { handleTranscript } = await import('../useWakeWord')
    await handleTranscript(new Blob(['x']))
    expect(answerSpy).toHaveBeenCalledWith('s1', '', 'yes')
    // sendAnswer 成功后会把回答写入记录（P4 的行为），文本取 option 的 label
    expect(store.messages.value).toHaveLength(1)
    expect(store.messages.value[0].role).toBe('user')
    expect(store.messages.value[0].text).toBe('允许本次')
  })

  /** 未命中选择 → 整段作为文本作答。 */
  it('未命中选项时作为文本作答', async () => {
    const { store, answerSpy } = await setup('随便吧')
    const { handleTranscript } = await import('../useWakeWord')
    await handleTranscript(new Blob(['x']))
    expect(answerSpy).toHaveBeenCalledWith('s1', '随便吧', undefined)
    expect(store.messages.value).toHaveLength(1)
    expect(store.messages.value[0].text).toBe('随便吧')
  })

  /** 无待答提问 → 维持原行为（写入 user 消息并开新一轮）。回归。 */
  it('无待答提问时维持原行为', async () => {
    const { store, answerSpy } = await setup('你好', { pending: false })
    const { handleTranscript } = await import('../useWakeWord')
    await handleTranscript(new Blob(['x']))
    expect(answerSpy).not.toHaveBeenCalled()
    expect(store.messages.value.some((m) => m.text === '你好')).toBe(true)
  })
})

/**
 * 播报期间暂停监听、播完恢复 —— 消除助手自己的声音自触发唤醒。
 * Listening pauses during playback and resumes after, so the assistant's own voice cannot
 * self-trigger the wake word.
 *
 * 注意：桩必须【有状态】—— isRunning 要反映 stop/start，否则「!isRunning() 才重启」
 * 的判定恒假、start() 永不调用，断言会假失败。
 */
describe('useWakeWord 播报门控', () => {
  function stubEngine() {
    let running = true
    const eng = {
      init: vi.fn(async () => true),
      start: vi.fn(async () => { running = true; return true }),
      stop: vi.fn(() => { running = false }),
      isRunning: vi.fn(() => running),
      isModelLoaded: vi.fn(() => true),
    }
    ;(globalThis as any).WakeWordEngine = eng
    return eng
  }

  beforeEach(() => {
    vi.resetModules()
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('no network')))
  })

  /** 播报开始 → 暂停引擎。Playback starting pauses the engine. */
  it('speaking 变 true 时停止引擎', async () => {
    const eng = stubEngine()
    const store = await import('../store')
    store.pendingQuestion.value = null
    const tts = await import('../useTts')
    await import('../useWakeWord')
    await nextTick()
    eng.stop.mockClear()

    tts.speaking.value = true
    await nextTick()
    expect(eng.stop).toHaveBeenCalledTimes(1)
    expect(eng.isRunning()).toBe(false)   // 桩确实转为未运行
  })

  /** 播报结束且无待答提问 → 恢复监听。Playback ending with no pending question resumes listening. */
  it('播报结束恢复监听', async () => {
    const eng = stubEngine()
    const store = await import('../store')
    store.pendingQuestion.value = null
    store.wakeEnabled.value = true
    const tts = await import('../useTts')
    await import('../useWakeWord')
    await nextTick()
    eng.start.mockClear()

    tts.speaking.value = true
    await nextTick()
    tts.speaking.value = false
    await nextTick()
    expect(eng.start).toHaveBeenCalledTimes(1)
  })

  /** 唤醒开关关闭时播完不重启（避免「关了唤醒却被动开麦」）。 */
  it('唤醒开关关闭时播完不重启', async () => {
    const eng = stubEngine()
    const store = await import('../store')
    store.pendingQuestion.value = null
    store.wakeEnabled.value = false
    const tts = await import('../useTts')
    await import('../useWakeWord')
    await nextTick()
    eng.start.mockClear()

    tts.speaking.value = true
    await nextTick()
    tts.speaking.value = false
    await nextTick()
    expect(eng.start).not.toHaveBeenCalled()
  })
})
