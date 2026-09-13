import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick } from 'vue'

/** 唤醒判定接入状态机：命中唤醒词且带指令 → 直接起一轮；只命中唤醒词 → 提示音后等下一段。
 *  Wiring the wake judgement into the state machine: a wake word plus command starts a turn
 *  immediately; a bare wake word chimes and treats the next segment as the command. */
describe('handleSegment 分流', () => {
  beforeEach(() => { vi.resetModules(); localStorage.clear() })

  async function setup(wakeResp: any) {
    const sent: string[] = []
    // transcribe 桩必须给出转写文本：「等指令」这一段走的是转写通道，桩若返回 undefined，
    // 「下一段当指令」的用例就永远拿不到指令可发（brief 原文是 vi.fn()，属笔误 —— 已就地补文本）。
    // The transcribe stub must yield a transcript: the "awaiting the command" segment goes through
    // the transcribe channel, and a stub returning undefined would leave that case with no command
    // to send at all. (The brief wrote a bare `vi.fn()`; fixed in place.)
    vi.doMock('../../../api', () => ({
      api: { wakeDetect: vi.fn(async () => wakeResp), transcribe: vi.fn(async () => ({ ok: true, text: '帮我查天气' })) },
    }))
    vi.doMock('../useChat', () => ({
      sendText: (t: string) => { sent.push(t) },
      sendAnswer: vi.fn(),
      runTurn: vi.fn(),
    }))
    vi.doMock('../useTts', () => ({ speaking: { value: false }, speakAuto: vi.fn() }))
    const mod = await import('../useWakeWord')
    return { mod, sent }
  }

  /** 唤醒词 + 指令 → 直接用后半段起一轮，不再多录一次。 */
  it('唤醒词带指令 → 直接发起一轮', async () => {
    const { mod, sent } = await setup({ ok: true, matched: true, command: '帮我查天气', text: '衍衡，帮我查天气。' })
    await mod.handleSegment(new Blob(['x']))
    expect(sent).toEqual(['帮我查天气'])
  })

  /** 只有唤醒词 → 不起轮，记为「等指令」，下一段直接当指令。 */
  it('只有唤醒词 → 下一段当指令', async () => {
    const { mod, sent } = await setup({ ok: true, matched: true, command: '', text: '衍衡。' })
    await mod.handleSegment(new Blob(['x']))
    expect(sent).toEqual([])
    // 下一段不再判定唤醒词，直接当指令
    await mod.handleSegment(new Blob(['x']))
    expect(sent.length).toBe(1)
  })

  /** 不命中 → 什么都不做（噪音/无关对话被丢弃）。 */
  it('不命中 → 丢弃', async () => {
    const { mod, sent } = await setup({ ok: true, matched: false, command: '', text: '今天天气怎么样。' })
    await mod.handleSegment(new Blob(['x']))
    expect(sent).toEqual([])
  })

  /** ASR 失败 → 不起轮，且计入失败次数。 */
  it('唤醒检测失败 → 丢弃并计数', async () => {
    const { mod, sent } = await setup({ ok: false, error: '上游 502' })
    await mod.handleSegment(new Blob(['x']))
    expect(sent).toEqual([])
  })

  /**
   * **待答提问优先**：这一段是「回答」，绝不能送去判唤醒词 —— 否则用户答「允许本次」会被
   * 当成不含唤醒词的噪音丢掉，P6 的语音作答功能就此失效。这是本任务最容易写错的地方。
   *
   * A pending question takes precedence: the segment is an *answer* and must never be sent to wake
   * detection, or answering "允许本次" would be discarded as noise that carries no wake word and
   * the whole voice-answering feature would silently stop working. This is the easiest thing to get
   * wrong here.
   */
  it('待答提问时走答案通道，不判唤醒词', async () => {
    vi.doMock('../../../api', () => ({
      api: {
        wakeDetect: vi.fn(async () => ({ ok: true, matched: true, command: 'X', text: 'X' })),
        transcribe: vi.fn(async () => ({ ok: true, text: '允许本次' })),
      },
    }))
    vi.doMock('../useChat', () => ({ sendText: vi.fn(), sendAnswer: vi.fn(), runTurn: vi.fn() }))
    vi.doMock('../useTts', () => ({ speaking: { value: false }, speakAuto: vi.fn() }))
    const { api } = await import('../../../api')
    const { sendAnswer } = await import('../useChat')
    const store = await import('../store')
    store.state.value = 'awaiting_answer'
    store.pendingQuestion.value = {
      text: '确认执行吗？', kind: 'choice',
      options: [{ value: 'yes', label: '允许本次' }, { value: 'no', label: '拒绝' }],
    }
    const { handleSegment } = await import('../useWakeWord')
    await handleSegment(new Blob(['x']))

    expect(vi.mocked(api.wakeDetect)).not.toHaveBeenCalled()
    expect(vi.mocked(sendAnswer)).toHaveBeenCalledWith('', 'yes')   // label 精确命中 → 回传 value
  })
})

/** 成本控制：节流与熔断 —— 误触发时不能疯狂刷云端接口（每次有人说话都是一次付费 ASR）。
 *  Cost control: throttling and the circuit breaker — a false trigger must not hammer the cloud
 *  endpoint (every segment with speech is a paid ASR call). */
describe('useWakeWord 成本控制', () => {
  beforeEach(() => { vi.resetModules(); localStorage.clear() })

  /** 装好桩与真实 store；`wakeDetect` 由调用方注入以便断言调用次数。
   *  Wire the stubs and the real store; the caller injects `wakeDetect` so the call count can be asserted. */
  async function setup(wakeDetect: any) {
    vi.doMock('../../../api', () => ({
      api: { wakeDetect, transcribe: vi.fn(async () => ({ ok: true, text: '你好' })) },
    }))
    vi.doMock('../useChat', () => ({ sendText: vi.fn(), sendAnswer: vi.fn(), runTurn: vi.fn() }))
    vi.doMock('../useTts', () => ({ speaking: { value: false }, speakAuto: vi.fn() }))
    const store = await import('../store')
    const mod = await import('../useWakeWord')
    return { mod, store, api: { wakeDetect } }
  }

  /** 两段之间的间隔小于 upload_throttle_ms → 第二段不上传。 */
  it('节流：间隔小于 upload_throttle_ms 的连续段只上传一次', async () => {
    const { mod, store, api } = await setup(vi.fn(async () => ({ ok: true, matched: false, command: '', text: '噪音' })))
    store.vadConfig.upload_throttle_ms = 500

    await mod.handleSegment(new Blob(['x']))
    await mod.handleSegment(new Blob(['x']))

    expect(api.wakeDetect).toHaveBeenCalledTimes(1)
  })

  /** 连续失败达阈值 → 停上传并明确提示（spec「错误与降级」：不静默失败）。 */
  it('熔断：连续 3 次失败后停止上传并提示', async () => {
    const { mod, store, api } = await setup(vi.fn(async () => ({ ok: false, error: '上游 502' })))
    store.vadConfig.upload_throttle_ms = 0   // 关掉节流，单独验熔断。Throttle off so only the breaker is under test.

    for (let i = 0; i < 5; i++) await mod.handleSegment(new Blob(['x']))

    expect(api.wakeDetect).toHaveBeenCalledTimes(3)
    expect(store.statusLine.value).toContain('云端唤醒不可用')
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
 * 播报门控与开启路径共用的桩：可断言的麦克风流、flush、以及一整套 getUserMedia/录音器/依赖模块的替身。
 *
 * 共用一份而不是每个 describe 各写一套 —— 同一份夹具的两份拷贝会各自漂移，
 * 而这里要断言的恰恰是「取流与录音器的生命周期只有一处实现」。
 *
 * Shared fixtures for the playback gate and the enable path: an assertable mic stream, flush, and a
 * full set of getUserMedia / recorder / dependency-module doubles.
 *
 * Shared rather than copied per describe: two copies of one fixture drift apart, and what is under
 * assertion here is precisely that the stream-and-recorder lifecycle has a single implementation.
 */

/** 可断言的麦克风流。An assertable mic stream. */
function makeStream() {
  const track = { stop: vi.fn() }
  return { getTracks: () => [track], track } as any
}

/** 等 watch 回调与其内部的异步分支（getUserMedia）跑完。
 *  Wait for the watch callback and its async branch (getUserMedia) to settle. */
async function flush() {
  await nextTick()
  await nextTick()
  await new Promise((r) => setTimeout(r, 0))
}

/**
 * 桩：录音器句柄、麦克风、依赖模块；返回真实 store 与本模块。
 * Stubs: recorder handles, mic, dependency modules; returns the real store and this module.
 *
 * @param opts.throwOnStart 建录音器时抛错（验开启路径的失败收尾）。Make recorder construction
 *   throw, to exercise the enable path's failed-startup tidy-up.
 */
async function setupWake(opts: { throwOnStart?: boolean } = {}) {
  const handles: any[] = []
  vi.doMock('../useSegmentRecorder', () => ({
    createSegmentRecorder: (stream: any, o: any) => {
      if (opts.throwOnStart) throw new Error('AudioContext unavailable')
      const h = { start: vi.fn(), stop: vi.fn(), isRecording: () => false, stream, opts: o }
      handles.push(h)
      return h
    },
  }))
  const streams: any[] = []
  /** 下一次 getUserMedia 是否挂起（用手动放行模拟真实取流耗时，权限弹窗时可达数秒）。
   *  Whether the next getUserMedia hangs (a manual release stands in for real acquisition latency,
   *  which can be seconds while a permission prompt is up). */
  let deferNext = false
  const pending: Array<(s: any) => void> = []
  const getUserMedia = vi.fn(async () => {
    if (deferNext) {
      deferNext = false
      return new Promise<any>((res) => pending.push(res))
    }
    const s = makeStream()
    streams.push(s)
    return s
  })
  vi.stubGlobal('navigator', {
    mediaDevices: {
      enumerateDevices: vi.fn(async () => [{ kind: 'audioinput', label: 'mic' }]),
      getUserMedia,
    },
  })
  vi.doMock('../../../api', () => ({ api: { wakeDetect: vi.fn(), transcribe: vi.fn() } }))
  vi.doMock('../useChat', () => ({ sendText: vi.fn(), sendAnswer: vi.fn(), runTurn: vi.fn() }))
  vi.doMock('../useTts', async () => {
    const { ref } = await import('vue')
    return { speaking: ref(false), speakAuto: vi.fn() }
  })
  const store = await import('../store')
  const tts = await import('../useTts')
  const ww = await import('../useWakeWord')
  return {
    store, ww, handles, streams, getUserMedia,
    speaking: tts.speaking as any,
    defer: () => { deferNext = true },
    release: (s: any) => { pending.shift()?.(s) },
  }
}

/**
 * 播报期间暂停监听、播完恢复 —— 消除助手自己的声音自触发唤醒。
 *
 * 实现已从「停/起 Vosk 引擎」改为「停/起分段录音器」：暂停时**释放麦克风轨道**，
 * 恢复时重新取流并**新建**一个分段录音器。新建而非复用是关键 —— 旧实例的迟到 onstop
 * 只可能改到它自己的记账，碰不到新实例（旧实例的 suppressed 仍为 true，也不会再回调上传）。
 *
 * Listening pauses during playback and resumes after, so the assistant's own voice cannot
 * self-trigger the wake word.
 *
 * The implementation moved from stopping/starting the Vosk engine to stopping/starting the
 * segment recorder: a pause **releases the mic tracks**, a resume re-acquires the stream and
 * builds a **fresh** segment recorder. Building fresh rather than reusing matters: a late onstop
 * from the old instance can only touch its own bookkeeping, never the new one's (and the old
 * instance's `suppressed` flag still holds, so it cannot emit either).
 */
describe('useWakeWord 播报门控', () => {
  beforeEach(() => { vi.resetModules(); localStorage.clear() })

  /** 播报开始 → 停掉分段录音器并释放麦克风轨道。Playback starting stops the recorder and releases the mic. */
  it('播报开始 → 停止分段录音并释放麦克风', async () => {
    const { ww, handles, streams, speaking } = await setupWake()
    await ww.toggleWake()
    expect(handles).toHaveLength(1)
    expect(handles[0].start).toHaveBeenCalledTimes(1)

    speaking.value = true
    await flush()

    expect(handles[0].stop).toHaveBeenCalledTimes(1)
    expect(streams[0].track.stop).toHaveBeenCalled()   // 麦克风确实被释放。The mic really was released.
  })

  /** 播报结束且无待答提问 → 重新取流并新建录音器，恢复聆听。
   *  Playback ending with no pending question re-acquires the stream, builds a new recorder and listens again. */
  it('播报结束且无待答提问 → 重新取流恢复监听', async () => {
    const { store, ww, handles, getUserMedia, speaking } = await setupWake()
    await ww.toggleWake()
    store.pendingQuestion.value = null

    speaking.value = true
    await flush()
    speaking.value = false
    await flush()

    expect(getUserMedia).toHaveBeenCalledTimes(2)      // 首次启动 + 播报后恢复。Initial start plus post-playback resume.
    expect(handles).toHaveLength(2)                    // 新建而非复用旧实例。Fresh instance, not the stopped one.
    expect(handles[1].start).toHaveBeenCalledTimes(1)
    expect(store.state.value).toBe('listening')
  })

  /** 播报结束且**有待答提问** → 回到待答并恢复监听（既有语义，不得丢）。
   *  Playback ending with a pending question returns to awaiting_answer and resumes listening. */
  it('播报结束且有待答提问 → 回到待答并恢复监听', async () => {
    const { store, ww, handles, getUserMedia, speaking } = await setupWake()
    await ww.toggleWake()
    store.pendingQuestion.value = {
      text: '确认执行吗？', kind: 'choice',
      options: [{ value: 'yes', label: '允许本次' }],
    }
    store.state.value = 'thinking'   // 提问时 useChat 置的状态。The state useChat sets when a question arrives.

    speaking.value = true
    await flush()
    speaking.value = false
    await flush()

    expect(store.state.value).toBe('awaiting_answer')
    expect(getUserMedia).toHaveBeenCalledTimes(2)
    expect(handles).toHaveLength(2)
  })

  /** 唤醒开关关闭时播完不重启（避免「关了唤醒却被动开麦」）。 */
  it('唤醒开关关闭时播完不重新取流', async () => {
    const { store, getUserMedia, speaking } = await setupWake()
    store.wakeEnabled.value = false
    store.pendingQuestion.value = null

    speaking.value = true
    await flush()
    speaking.value = false
    await flush()

    expect(getUserMedia).not.toHaveBeenCalled()
  })

  /** 取流在途时又被暂停 → 迟到的那条流必须释放，且不得新建录音器（否则播报期间麦克风复活、
   *  助手自己的声音会自触发唤醒）。代际令牌就是为这条竞态而加。
   *  A pause landing while getUserMedia is in flight must release the late stream and must not build a
   *  recorder — otherwise the mic revives mid-playback and the assistant's own voice can wake it. */
  it('取流途中又被暂停 → 释放迟到的流且不新建录音器', async () => {
    const { ww, handles, speaking, defer, release } = await setupWake()
    await ww.toggleWake()          // 第 1 次取流成功。First acquisition succeeds.

    defer()                        // 第 2 次取流挂起。Second acquisition hangs.
    speaking.value = true
    await flush()                  // 暂停：释放流与录音器。Pause: releases stream and recorder.
    speaking.value = false
    await flush()                  // 恢复：取流在途。Resume: acquisition in flight.
    speaking.value = true
    await flush()                  // 播报又开始了。Playback starts again.

    const late = makeStream()
    release(late)                  // 放行迟到的流。Release the late stream.
    await flush()

    expect(late.track.stop).toHaveBeenCalled()
    expect(handles).toHaveLength(1)   // 没有新建录音器。No new recorder was built.
  })
})

/**
 * 等待窗口与收尾 —— 三条都是「定时器随 Vosk 引擎一起被删掉」造成的功能回归。
 *
 * 待答窗口：提问后一直不说话 → 进待机（README 与 P6 记载的行为），待机时再开口回到本题作答。
 * 等指令窗口：只说了唤醒词却没跟指令 → 窗口过后该段不再被当成指令执行（误触发不能变成执行）。
 * 收尾复位：一轮结束 3 秒后回聆听，界面不会永久停在「完成」。
 *
 * Wait windows and finishing touches — three functional regressions caused by the timers being
 * deleted along with the Vosk engine: the answer window (no reply → standby, as recorded in the
 * README and P6; speaking again from standby resumes *this* question), the command window (a bare
 * wake word must not turn a later unrelated segment into an executed command), and the post-turn
 * reset (done/error returns to listening after 3s instead of parking the UI on "完成").
 */
describe('useWakeWord 等待窗口与收尾', () => {
  beforeEach(() => { vi.resetModules(); localStorage.clear() })

  /** 装好桩与真实 store；调用方负责 fake/real 计时器的开关。
   *  Wire the stubs and the real store; the caller owns the fake/real timer switch. */
  async function setupWait(opts: { wake?: any; sent?: string[] } = {}) {
    const sent = opts.sent ?? []
    vi.doMock('../../../api', () => ({
      api: {
        wakeDetect: opts.wake ?? vi.fn(async () => ({ ok: true, matched: false, command: '', text: '' })),
        transcribe: vi.fn(async () => ({ ok: true, text: '允许本次' })),
      },
    }))
    vi.doMock('../useChat', () => ({
      sendText: (t: string) => { sent.push(t) },
      sendAnswer: vi.fn(),
      runTurn: vi.fn(),
    }))
    vi.doMock('../useTts', () => ({ speaking: { value: false }, speakAuto: vi.fn() }))
    const store = await import('../store')
    const chat = await import('../useChat')
    const mod = await import('../useWakeWord')
    store.vadConfig.upload_throttle_ms = 0   // 本组只测窗口，节流另有用例。Windows only here; throttling has its own case.
    return { store, mod, sent, sendAnswer: chat.sendAnswer as any, sendText: chat.sendText as any }
  }

  /** 待答窗口过期 → 进待机（走 wakeFsm 的 answer_timeout 迁移）；待机时再开口 → 回到本题作答。 */
  it('待答无应答 → 进待机；待机时再开口 → 回到本题作答', async () => {
    vi.useFakeTimers()
    try {
      const { store, mod, sendAnswer } = await setupWait()
      store.wakeEnabled.value = true              // 前提：语音作答只存在于监听开着的时候。Precondition: voice answering only exists while listening is on.
      store.pendingQuestion.value = {
        text: '确认执行吗？', kind: 'choice',
        options: [{ value: 'yes', label: '允许本次' }],
      }
      store.state.value = 'awaiting_answer'
      await nextTick()                            // 让 watch(state) 武装等待窗口。Let watch(state) arm the window.
      await vi.advanceTimersByTimeAsync(8000)

      expect(store.state.value).toBe('standby')

      // 待机时用户又开口（说唤醒词回到本题）→ 状态回到待答，这一段作为回答投递。
      // The user speaks again from standby (the wake word resumes this question): the state returns
      // to awaiting_answer and this segment is delivered as the answer.
      await mod.handleSegment(new Blob(['x']))
      expect(store.state.value).toBe('awaiting_answer')
      expect(sendAnswer).toHaveBeenCalledWith('', 'yes')
    } finally { vi.useRealTimers() }
  })

  /** 只说了唤醒词、没说指令 → 窗口过后，无关语音**不得**被当成指令执行。 */
  it('等指令过期 → 之后的无关语音不被当成指令执行', async () => {
    vi.useFakeTimers()
    try {
      const sent: string[] = []
      const wakeDetect = vi.fn()
        .mockResolvedValueOnce({ ok: true, matched: true, command: '', text: '衍衡。' })
        .mockResolvedValue({ ok: true, matched: false, command: '', text: '今天天气怎么样。' })
      const { store, mod } = await setupWait({ wake: wakeDetect, sent })

      await mod.handleSegment(new Blob(['x']))    // 裸唤醒词 → 进等指令窗口。Bare wake word → command window opens.
      expect(sent).toEqual([])

      await vi.advanceTimersByTimeAsync(8000)     // 窗口过期。The window expires.
      await mod.handleSegment(new Blob(['x']))    // 之后的无关语音。A later unrelated segment.

      expect(sent).toEqual([])                   // 不得被执行。Must not be executed.
      expect(wakeDetect).toHaveBeenCalledTimes(2)  // 回到正常唤醒判定。Back to normal wake detection.
      expect(store.statusLine.value).not.toContain('请说指令')
    } finally { vi.useRealTimers() }
  })

  /** 一轮结束（done/error）3 秒后回聆听，界面不会永久停在「完成」。 */
  it('一轮结束 3 秒后回到聆听', async () => {
    vi.useFakeTimers()
    try {
      const { store } = await setupWait()
      store.wakeEnabled.value = true
      store.state.value = 'done'
      await nextTick()
      expect(store.state.value).toBe('done')      // 3 秒内不动。Unchanged within three seconds.

      await vi.advanceTimersByTimeAsync(3000)
      expect(store.state.value).toBe('listening')
    } finally { vi.useRealTimers() }
  })
})

/**
 * 开启路径的重入与失败收尾。
 *
 * 取流期间（权限弹窗时长达数秒）状态仍是 idle/done/error，所以连点两次会**两次进入开启分支**：
 * 两条流、两台录音器，而 stopListening 只持有最新那个 —— 被孤立的那台会一直录、一直上传，
 * 直到页面结束。这正是本重构要消除的「麦开着却没人听」。
 *
 * Re-entry and failed-startup tidy-up on the enable path. While the stream is being acquired (seconds
 * long behind a permission prompt) the state is still idle/done/error, so a double click enters the
 * enable branch **twice**: two streams, two recorders, while stopListening only holds the newest —
 * the orphan keeps recording and uploading until the page dies, exactly the "mic open with nobody
 * listening" failure this rework removes.
 */
describe('useWakeWord 开启路径', () => {
  beforeEach(() => { vi.resetModules(); localStorage.clear() })

  /** 并发重入：只采集一次；关闭时所有流与录音器都被收掉。 */
  it('并发重入开启 → 只采集一次，关闭时收掉全部流与录音器', async () => {
    const { ww, handles, streams, getUserMedia, defer, release } = await setupWake()

    defer()                                  // 第一次取流挂起。First acquisition hangs.
    const p1 = ww.toggleWake()
    const p2 = ww.toggleWake()               // 用户等权限弹窗时又点了一次。The user clicks again.
    await flush()

    // 不变量：重入不得再起第二条采集。
    // Invariant: a re-entry must not start a second acquisition.
    expect(getUserMedia).toHaveBeenCalledTimes(1)

    const s1 = makeStream()
    release(s1)                              // 放行第一条流。Release the first stream.
    await p1
    await p2

    expect(handles).toHaveLength(1)
    expect(handles[0].start).toHaveBeenCalledTimes(1)

    await ww.toggleWake()                    // 关掉唤醒。Switch wake off.

    // 收干净：采集到的每一条流都被关掉，没有一台录音器还在跑（否则它还在上传）。
    // Everything collected is released: every stream closed and no recorder left running (a running
    // recorder is still uploading).
    expect([...streams, s1].every((s) => s.track.stop.mock.calls.length === 1)).toBe(true)
    expect(handles.every((h) => h.stop.mock.calls.length === 1)).toBe(true)
  })

  /** 启动抛错：不得留下活着的麦克风流，也不得让 wakeEnabled 与真实状态不一致。 */
  it('启动抛错 → 释放麦克风且不谎报已开启', async () => {
    const { store, ww, handles, streams } = await setupWake({ throwOnStart: true })

    await ww.toggleWake()                    // 不得抛出：异常必须被收在开启路径里。Must not reject.

    expect(handles).toHaveLength(0)
    expect(streams.every((s) => s.track.stop.mock.calls.length === 1)).toBe(true)   // 流已释放。Stream released.
    expect(store.wakeEnabled.value).toBe(false)
    expect(store.state.value).toBe('error')  // failWake：明确提示，不静默。Loud, never silent.
  })

  /**
   * 录音器**已经活着**时又进开启分支 —— 无需并发，一次单击即可：
   * `useChat` 每轮结束把状态置为 `done`，要等 3 秒复位回 `listening`，这个窗口里点一下悬浮球，
   * 开启分支照样被进入（state 是 done、闸是 false），于是又取一条流、又建一台录音器，
   * 把原来那台连同它的流一起孤立 —— `stopListening()` 只持有最新那个，够不到它们。
   *
   * Entering the enable branch while a recorder is **already live** needs no concurrency at all:
   * useChat parks the state at `done` after every turn until the 3s reset, and a click inside that
   * window still enters the enable branch (state is `done`, the latch is false), acquiring a second
   * stream and a second recorder and orphaning the first — stopListening only holds the newest.
   */
  it('聆听中单击开启 → 复用现有录音器，不再采集第二条流', async () => {
    const { store, ww, handles, streams, getUserMedia } = await setupWake()

    await ww.toggleWake()                    // 开启：一条流、一台录音器。Enable: one stream, one recorder.
    expect(handles).toHaveLength(1)

    store.state.value = 'done'               // 回合结束后的 3 秒窗口。The 3s window after a turn.
    await ww.toggleWake()                    // 这个窗口里点一下悬浮球。A click inside that window.

    expect(getUserMedia).toHaveBeenCalledTimes(1)   // 不得再取一条流。No second acquisition.
    expect(handles).toHaveLength(1)                 // 不得再建一台录音器。No second recorder.
    expect(handles[0].start).toHaveBeenCalledTimes(1)
    expect(store.state.value).toBe('listening')     // 回到聆听，而不是空闲。Back to listening.

    await ww.toggleWake()                    // 关掉唤醒。Switch wake off.

    // 收干净：这一段里产生的每条流都被关掉，没有一台录音器还在跑。
    // Everything produced here is released: every stream closed, no recorder left running.
    expect(streams.every((s) => s.track.stop.mock.calls.length === 1)).toBe(true)
    expect(handles.every((h) => h.stop.mock.calls.length === 1)).toBe(true)
  })

  /**
   * 两条取流同时在途：播报结束的恢复与紧随其后的一次单击（真会撞上 —— 回合结束的 done 窗口与
   * 播报尾音重叠时，暂停把录音器清空、两条路径都能看到「没有录音器」）。先写入者赢，后到的那条
   * 流必须当场释放，绝不能覆盖槽位 —— 覆盖就孤立出前台那台录音器 + 一条一直开着的流。
   *
   * Two acquisitions in flight at once: the post-playback resume and a click right after it (they
   * genuinely overlap — while a finished turn's `done` window meets the tail of playback, the pause
   * empties the recorder slot and both paths see "no recorder"). First writer wins; the late stream
   * must be released on the spot, never written over the slot, or the recorder already running plus
   * a permanently open stream get orphaned.
   */
  it('取流在途时又单击开启 → 先到者胜，迟到的流被释放', async () => {
    const { store, ww, handles, streams, getUserMedia, speaking, defer, release } = await setupWake()

    await ww.toggleWake()                    // 开启：第 1 条流。Enable: stream #1.
    speaking.value = true
    await flush()                            // 播报开始 → 暂停（槽位清空，代际推进）。Pause.
    store.state.value = 'done'               // 回合结束状态与播报尾音重叠。The done window.

    defer()                                  // 恢复那条取流挂起。The resume's acquisition hangs.
    speaking.value = false
    await flush()
    defer()                                  // 单击那条取流也挂起。The click's acquisition hangs too.
    const click = ww.toggleWake()
    await flush()

    expect(getUserMedia).toHaveBeenCalledTimes(3)   // 初始 + 恢复 + 单击。Initial + resume + click.

    const sResume = makeStream()
    release(sResume)                         // 先放行恢复那条。Release the resume's stream first.
    await flush()
    const sClick = makeStream()
    release(sClick)                          // 再放行单击那条。Then the click's.
    await click
    await flush()

    expect(handles).toHaveLength(2)          // 初始 1 + 恢复 1；单击不得再建。No third recorder.
    expect(sClick.track.stop).toHaveBeenCalledTimes(1)   // 迟到的那条流被释放。Late stream released.

    await ww.toggleWake()                    // 关掉唤醒。Switch wake off.

    expect(handles.every((h) => h.stop.mock.calls.length === 1)).toBe(true)
    expect([...streams, sResume, sClick].every((s) => s.track.stop.mock.calls.length === 1)).toBe(true)
  })
})
