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

  /** 桩：录音器句柄、麦克风、依赖模块；返回真实 store 与本模块。
   *  Stubs: recorder handles, mic, dependency modules; returns the real store and this module. */
  async function setup() {
    const handles: any[] = []
    vi.doMock('../useSegmentRecorder', () => ({
      createSegmentRecorder: (stream: any, opts: any) => {
        const h = { start: vi.fn(), stop: vi.fn(), isRecording: () => false, stream, opts }
        handles.push(h)
        return h
      },
    }))
    const streams: any[] = []
    /** 下一次 getUserMedia 是否挂起（用手动放行模拟真实取流耗时）。
     *  Whether the next getUserMedia hangs (a manual release stands in for real acquisition latency). */
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

  beforeEach(() => { vi.resetModules(); localStorage.clear() })

  /** 播报开始 → 停掉分段录音器并释放麦克风轨道。Playback starting stops the recorder and releases the mic. */
  it('播报开始 → 停止分段录音并释放麦克风', async () => {
    const { ww, handles, streams, speaking } = await setup()
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
    const { store, ww, handles, getUserMedia, speaking } = await setup()
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
    const { store, ww, handles, getUserMedia, speaking } = await setup()
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
    const { store, getUserMedia, speaking } = await setup()
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
    const { ww, handles, speaking, defer, release } = await setup()
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
