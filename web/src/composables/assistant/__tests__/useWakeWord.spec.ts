import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick } from 'vue'

/** 唤醒判定接入状态机：命中唤醒词且带指令 → 直接起一轮；只命中唤醒词 → 提示音后等下一段。
 *  Wiring the wake judgement into the state machine: a wake word plus command starts a turn
 *  immediately; a bare wake word chimes and treats the next segment as the command. */
describe('handleSegment 分流', () => {
  beforeEach(() => { vi.resetModules(); localStorage.clear() })

  async function setup(wakeResp: any, checkResp?: any) {
    const sent: string[] = []
    // transcribe 桩必须给出转写文本：「等指令」这一段走的是转写通道，桩若返回 undefined，
    // 「下一段当指令」的用例就永远拿不到指令可发（brief 原文是 vi.fn()，属笔误 —— 已就地补文本）。
    // The transcribe stub must yield a transcript: the "awaiting the command" segment goes through
    // the transcribe channel, and a stub returning undefined would leave that case with no command
    // to send at all. (The brief wrote a bare `vi.fn()`; fixed in place.)
    //
    // wakeCheck 是新的本地 KWS 快检（判定先行）；wakeDetect 退居后台提取（提取尾随指令）。
    // wakeCheck is the new local KWS quick check (verdict first); wakeDetect demoted to
    // background extraction (pulling the trailing command).
    vi.doMock('../../../api', () => ({
      api: {
        wakeCheck: vi.fn(async () => checkResp ?? { ok: true, hit: true, bypass: false }),
        wakeDetect: vi.fn(async () => wakeResp),
        transcribe: vi.fn(async () => ({ ok: true, text: '帮我查天气' })),
      },
    }))
    vi.doMock('../useChat', () => ({
      sendText: (t: string) => { sent.push(t) },
      sendAnswer: vi.fn(),
      runTurn: vi.fn(),
    }))
    vi.doMock('../useTts', () => ({ speaking: { value: false }, speakAuto: vi.fn(), stopSpeak: vi.fn() }))
    const mod = await import('../useWakeWord')
    return { mod, sent }
  }

  /** 唤醒词 + 指令 → 后台提取到指令后直接起一轮（一句话场景）。 */
  it('唤醒词带指令 → 提取后直接发起一轮', async () => {
    const { mod, sent } = await setup({ ok: true, matched: true, command: '帮我查天气', text: '衍衡，帮我查天气。' })
    await mod.handleSegment(new Blob(['x']))
    await new Promise((r) => setTimeout(r, 0))   // 等后台提取 settle。Let the background extraction settle.
    expect(sent).toEqual(['帮我查天气'])
  })

  /** 只有唤醒词 → 不起轮，记为「等指令」，下一段直接当指令。 */
  it('只有唤醒词 → 下一段当指令', async () => {
    const { mod, sent } = await setup({ ok: true, matched: true, command: '', text: '衍衡。' })
    await mod.handleSegment(new Blob(['x']))
    await new Promise((r) => setTimeout(r, 0))   // 提取为空 → 窗口保持。Extraction empty → window stays.
    expect(sent).toEqual([])
    // 下一段不再判定唤醒词，直接当指令
    await mod.handleSegment(new Blob(['x']))
    expect(sent.length).toBe(1)
  })

  /** 快检未命中 → 什么都不做（噪音/无关对话被丢弃，不调云端提取）。
   *  A quick-check miss drops the clip outright (no background extraction call). */
  it('快检未命中 → 丢弃且不提取', async () => {
    const { mod, sent } = await setup(
      { ok: true, matched: true, command: 'X', text: 'X' },   // 提取桩给「会命中」的假结果
      { ok: true, hit: false, bypass: false },               // 但快检未命中 → 提取根本不该被调
    )
    await mod.handleSegment(new Blob(['x']))
    await new Promise((r) => setTimeout(r, 0))
    expect(sent).toEqual([])
    const { api } = await import('../../../api')
    expect(vi.mocked(api.wakeDetect)).not.toHaveBeenCalled()
  })

  /** 快检失败 → 丢弃并计入失败次数（熔断计数）。
   *  A quick-check failure drops the clip and counts toward the breaker. */
  it('快检失败 → 丢弃并计数', async () => {
    const { mod, sent } = await setup(
      { ok: true, matched: true, command: 'X', text: 'X' },
      { ok: false },
    )
    await mod.handleSegment(new Blob(['x']))
    expect(sent).toEqual([])
    const { api } = await import('../../../api')
    expect(vi.mocked(api.wakeDetect)).not.toHaveBeenCalled()
  })

  /** 快检旁路（KWS 模型缺失）→ 回退完整云端判定路径，不丢唤醒。
   *  A quick-check bypass (KWS model missing) falls back to the full cloud path — never loses the wake. */
  it('快检旁路 → 回退完整判定路径', async () => {
    const { mod, sent } = await setup(
      { ok: true, matched: true, command: '帮我查天气', text: '衍衡，帮我查天气。' },
      { ok: true, hit: false, bypass: true },
    )
    await mod.handleSegment(new Blob(['x']))
    expect(sent).toEqual(['帮我查天气'])   // 走完整路径：判定+切分直接出结果
  })

  /** 动作先行：快检命中后立即进等指令窗口，**不等**后台提取返回。
   *  Act first: the command window opens as soon as the check hits, without waiting
   *  for the background extraction to return. */
  it('快检命中 → 立即进等指令窗口（不等提取）', async () => {
    let release!: (v: any) => void
    const wakeDetect = vi.fn(() => new Promise<any>((res) => { release = res }))   // 提取挂着不返回
    vi.doMock('../../../api', () => ({
      api: {
        wakeCheck: vi.fn(async () => ({ ok: true, hit: true, bypass: false })),
        wakeDetect,
        transcribe: vi.fn(async () => ({ ok: true, text: '帮我查天气' })),
      },
    }))
    vi.doMock('../useChat', () => ({ sendText: vi.fn(), sendAnswer: vi.fn(), runTurn: vi.fn() }))
    vi.doMock('../useTts', () => ({ speaking: { value: false }, speakAuto: vi.fn(), stopSpeak: vi.fn() }))
    const store = await import('../store')
    const mod = await import('../useWakeWord')
    store.state.value = 'listening'

    await mod.handleSegment(new Blob(['x']))    // 提取仍挂起，窗口必须已开
    expect(store.state.value).toBe('recording')
    expect(store.statusLine.value).toContain('请说指令')

    release({ ok: true, matched: true, command: '', text: '衍衡。' })   // 迟来的提取：无指令，无副作用
  })

  /** 竞态护栏：指令段消费后，迟到的尾随提取结果必须被丢弃（防止双重执行）。
   *  Race guard: once a segment has been consumed as the command, a late trailing-extraction
   *  result must be discarded (no double execution). */
  it('指令段消费后迟到的提取被丢弃', async () => {
    vi.useFakeTimers()
    try {
      let release!: (v: any) => void
      const wakeDetect = vi.fn(() => new Promise<any>((res) => { release = res }))
      vi.doMock('../../../api', () => ({
        api: {
          wakeCheck: vi.fn(async () => ({ ok: true, hit: true, bypass: false })),
          wakeDetect,
          transcribe: vi.fn(async () => ({ ok: true, text: '查天气' })),
        },
      }))
      vi.doMock('../useChat', () => ({ sendText: (t: string) => { sent.push(t) }, sendAnswer: vi.fn(), runTurn: vi.fn() }))
      vi.doMock('../useTts', () => ({ speaking: { value: false }, speakAuto: vi.fn(), stopSpeak: vi.fn() }))
      const sent: string[] = []
      const store = await import('../store')
      const mod = await import('../useWakeWord')
      store.state.value = 'listening'

      await mod.handleSegment(new Blob(['x']))        // 裸唤醒词 → 窗口开，提取挂起
      await mod.handleSegment(new Blob(['x']))        // 第二段被消费为指令 → sendText('查天气')
      expect(sent).toEqual(['查天气'])

      release({ ok: true, matched: true, command: '挂起期间冒出的指令', text: 'X' })
      await vi.advanceTimersByTimeAsync(0)
      expect(sent).toEqual(['查天气'])               // 迟到提取被丢弃，不得追加执行
    } finally { vi.useRealTimers() }
  })

  /** 双重执行竞态（本项目实际踩过的 bug）：指令段转写在途时后台提取先返回 ——
   *  两者都带「同一句」时只能执行一次。The double-execution race this project actually
   *  hit: the extraction resolves while the command segment's transcription is still in
   *  flight — when both carry the same utterance, it must run exactly once. */
  it('提取与指令段转写同时在途 → 只执行一次', async () => {
    vi.useFakeTimers()
    try {
      let releaseExtract!: (v: any) => void
      let releaseTranscribe!: (v: any) => void
      const wakeDetect = vi.fn(() => new Promise<any>((res) => { releaseExtract = res }))
      const transcribe = vi.fn(() => new Promise<any>((res) => { releaseTranscribe = res }))
      vi.doMock('../../../api', () => ({
        api: {
          wakeCheck: vi.fn(async () => ({ ok: true, hit: true, bypass: false })),
          wakeDetect,
          transcribe,
        },
      }))
      vi.doMock('../useChat', () => ({ sendText: (t: string) => { sent.push(t) }, sendAnswer: vi.fn(), runTurn: vi.fn() }))
      vi.doMock('../useTts', () => ({ speaking: { value: false }, speakAuto: vi.fn(), stopSpeak: vi.fn() }))
      const sent: string[] = []
      const store = await import('../store')
      const mod = await import('../useWakeWord')
      store.state.value = 'listening'

      await mod.handleSegment(new Blob(['x']))   // 裸唤醒词 → 窗口开，提取挂起
      const p = mod.handleSegment(new Blob(['x']))   // 指令段 → 转写挂起（尚未认领）

      releaseExtract({ ok: true, matched: true, command: '查天气', text: '衍衡，查天气' })
      await vi.advanceTimersByTimeAsync(0)       // 提取先回来 → 认领 → 发送

      releaseTranscribe({ ok: true, text: '查天气' })
      await p
      await vi.advanceTimersByTimeAsync(0)

      expect(sent).toEqual(['查天气'])           // 恰好一次，不得两连发（两份响应 = 重复音频）
    } finally { vi.useRealTimers() }
  })

  /** TTS 回声护栏：播报结束后的尾音/回声段必须整体丢弃 —— 助手自称「衍衡」，
   *  拾到就误唤醒 → 新回合掐死待答问题 → 新回应再回声（连锁循环的根）。
   *  Echo guard: segments in the post-playback window must be dropped — the assistant
   *  calls itself 衍衡, catching it false-wakes, kills the pending question with a new
   *  turn, and the new response echoes again (the root of the cascade). */
  it('播报结束后的回声段被丢弃（不唤醒、不代答）', async () => {
    vi.useFakeTimers()
    try {
      const sent: string[] = []
      vi.doMock('../../../api', () => ({
        api: {
          wakeCheck: vi.fn(async () => ({ ok: true, hit: true, bypass: false })),
          wakeDetect: vi.fn(async () => ({ ok: true, matched: true, command: '打开网页', text: '衍衡打开网页' })),
          transcribe: vi.fn(async () => ({ ok: true, text: '不要回答我' })),
        },
      }))
      vi.doMock('../useChat', () => ({ sendText: (t: string) => { sent.push(t) }, sendAnswer: vi.fn(), runTurn: vi.fn() }))
      // speaking 必须是响应式 ref：orchestrator 的 watch 挂在它上面（回声护栏由该 watch 武装）。
      // speaking must be a reactive ref: the orchestrator's watch hangs on it (it arms the echo guard).
      const { ref } = await import('vue')
      const speaking = ref(false)
      vi.doMock('../useTts', () => ({ speaking, speakAuto: vi.fn(), stopSpeak: vi.fn() }))
      const store = await import('../store')
      const mod = await import('../useWakeWord')

      // 模拟一次播报结束（watch 播报门控 → 启动回声护栏）。
      // Simulate a playback ending (the speaking watch arms the echo guard).
      speaking.value = true
      await nextTick()
      speaking.value = false
      await nextTick()

      await mod.handleSegment(new Blob(['x']))   // 回声窗口内的段
      await vi.advanceTimersByTimeAsync(0)
      expect(sent).toEqual([])                    // 不得唤醒/发送
      const { api } = await import('../../../api')
      expect(vi.mocked(api.wakeCheck)).not.toHaveBeenCalled()

      await vi.advanceTimersByTimeAsync(1300)    // 窗口过后恢复
      await mod.handleSegment(new Blob(['x']))
      await vi.advanceTimersByTimeAsync(0)
      expect(sent).toEqual(['打开网页'])
    } finally { vi.useRealTimers() }
  })

  /** 段串行化：背靠背的段不得交错穿透 await 空隙双重触发（重复执行/重复录音）。
   *  Segment serialization: back-to-back segments must not interleave through the await
   *  gaps and double-fire (repeated execution / repeated recording prompts). */
  it('背靠背段串行处理，不双重触发', async () => {
    const sent: string[] = []
    let active = 0
    let maxActive = 0
    const wakeCheck = vi.fn(async () => {
      active++; maxActive = Math.max(maxActive, active)
      await new Promise((r) => setTimeout(r, 30))   // 制造 await 空隙
      active--
      return { ok: true, hit: true, bypass: false }
    })
    vi.doMock('../../../api', () => ({
      api: {
        wakeCheck,
        wakeDetect: vi.fn(async () => ({ ok: true, matched: true, command: 'X', text: '衍衡X' })),
        transcribe: vi.fn(async () => ({ ok: true, text: 'Y' })),
      },
    }))
    vi.doMock('../useChat', () => ({ sendText: (t: string) => { sent.push(t) }, sendAnswer: vi.fn(), runTurn: vi.fn() }))
    vi.doMock('../useTts', () => ({ speaking: { value: false }, speakAuto: vi.fn(), stopSpeak: vi.fn() }))
    const store = await import('../store')
    const mod = await import('../useWakeWord')
    store.vadConfig.upload_throttle_ms = 0

    void mod.handleSegment(new Blob(['x']))
    void mod.handleSegment(new Blob(['x']))
    await new Promise((r) => setTimeout(r, 200))

    expect(maxActive).toBe(1)   // 任意时刻只有一个段在处理中
    expect(sent).toEqual(['X'])  // 提取只认领一次
  })

  /** 语音作答后陈旧超时不得再把状态踢进待机（回答完成后不再冒出录音/待答）。
   *  场景：作答已投递，但前端状态停留在 awaiting_answer（回合继续、状态未变）——
   *  8 秒前武装的超时若不清掉，会把状态踢进 standby，待机再开口就回到待答录音界面。
   *  A stale answer timeout must not yank the state into standby after the answer was
   *  delivered: the answer is in, but the state still sits on awaiting_answer (the turn
   *  continues without a state change) — the timer armed 8s earlier must be defused. */
  it('作答后陈旧应答超时不再把状态踢进待机', async () => {
    vi.useFakeTimers()
    try {
      vi.doMock('../../../api', () => ({
        api: {
          wakeCheck: vi.fn(async () => ({ ok: true, hit: true, bypass: false })),
          wakeDetect: vi.fn(async () => ({ ok: true, matched: false, command: '', text: '' })),
          transcribe: vi.fn(async () => ({ ok: true, text: '允许本次' })),
        },
      }))
      vi.doMock('../useChat', () => ({ sendText: vi.fn(), sendAnswer: vi.fn(), runTurn: vi.fn() }))
      vi.doMock('../useTts', () => ({ speaking: { value: false }, speakAuto: vi.fn(), stopSpeak: vi.fn() }))
      const store = await import('../store')
      const mod = await import('../useWakeWord')
      store.wakeEnabled.value = true
      store.pendingQuestion.value = {
        text: '确认执行吗？', kind: 'choice',
        options: [{ value: 'yes', label: '允许本次' }],
      }
      store.state.value = 'awaiting_answer'
      await nextTick()
      await mod.handleSegment(new Blob(['x']))   // 作答 → 认领 + 清掉陈旧定时器

      expect(store.state.value).toBe('awaiting_answer')   // 状态未变（回合继续中）
      await vi.advanceTimersByTimeAsync(9000)             // 越过原 8s 超时点
      expect(store.state.value).toBe('awaiting_answer')   // 不得被踢进 standby
    } finally { vi.useRealTimers() }
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
        wakeCheck: vi.fn(async () => ({ ok: true, hit: true, bypass: false })),
        wakeDetect: vi.fn(async () => ({ ok: true, matched: true, command: 'X', text: 'X' })),
        transcribe: vi.fn(async () => ({ ok: true, text: '允许本次' })),
      },
    }))
    vi.doMock('../useChat', () => ({ sendText: vi.fn(), sendAnswer: vi.fn(), runTurn: vi.fn() }))
    vi.doMock('../useTts', () => ({ speaking: { value: false }, speakAuto: vi.fn(), stopSpeak: vi.fn() }))
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

    expect(vi.mocked(api.wakeCheck)).not.toHaveBeenCalled()
    expect(vi.mocked(api.wakeDetect)).not.toHaveBeenCalled()
    // label 精确命中 → 回传 value（source=voice 供审计）；第4参为段落捕获的问题快照。
    expect(vi.mocked(sendAnswer)).toHaveBeenCalledWith(
      '', 'yes', 'voice', expect.objectContaining({ text: '确认执行吗？' }),
    )
  })

  /**
   * **作答绑定段落捕获的问题快照**（修「回答和问题分开」）：云端转写要等数秒，期间
   * pendingQuestion 可能被清（流错误/中止竞态）。段落入口已捕获 pq —— 转写完成后
   * 必须把快照传给 sendAnswer，让 qid 与贴块以捕获时的问题为准；若让 sendAnswer
   * 重读 store，清空后 qid 丢失 → 投递无 qid + 走独立用户气泡兜底 → 问答分开。
   *
   * The answer binds to the question snapshot captured at segment entry (fixes "the
   * answer and the question are split apart"): cloud ASR takes seconds and
   * pendingQuestion may be cleared meanwhile (stream error / abort race). The entry
   * point already captured pq — after transcription it must hand that snapshot to
   * sendAnswer so the qid and attach target the question as captured. If sendAnswer
   * re-read the store instead, a cleared store loses the qid → a qid-less POST plus
   * the standalone-user-bubble fallback → Q and A split apart. */
  it('转写期间 pendingQuestion 被清，作答仍带捕获快照的 qid', async () => {
    const hooks: { clear?: () => void } = {}
    vi.doMock('../../../api', () => ({
      api: {
        wakeCheck: vi.fn(async () => ({ ok: true, hit: true, bypass: false })),
        wakeDetect: vi.fn(async () => ({ ok: true, matched: false, command: '', text: '' })),
        transcribe: vi.fn(async () => {
          hooks.clear?.()   // 转写窗口内：流错误清空 pendingQuestion（竞态注入）。
          return { ok: true, text: '允许本次' }
        }),
      },
    }))
    vi.doMock('../useChat', () => ({ sendText: vi.fn(), sendAnswer: vi.fn(), runTurn: vi.fn() }))
    vi.doMock('../useTts', () => ({ speaking: { value: false }, speakAuto: vi.fn(), stopSpeak: vi.fn() }))
    const { sendAnswer } = await import('../useChat')
    const store = await import('../store')
    store.state.value = 'awaiting_answer'
    store.pendingQuestion.value = {
      text: '确认执行吗？', kind: 'choice',
      options: [{ value: 'yes', label: '允许本次' }, { value: 'no', label: '拒绝' }],
      qid: 'q_snap',
    }
    hooks.clear = () => { store.pendingQuestion.value = null }
    const { handleSegment } = await import('../useWakeWord')
    await handleSegment(new Blob(['x']))

    expect(vi.mocked(sendAnswer)).toHaveBeenCalledWith(
      '', 'yes', 'voice',
      expect.objectContaining({ qid: 'q_snap', options: expect.any(Array) }),
    )
  })
})

/** 成本控制：节流与熔断 —— 误触发时不能疯狂刷云端接口（每次有人说话都是一次付费 ASR）。
 *  Cost control: throttling and the circuit breaker — a false trigger must not hammer the cloud
 *  endpoint (every segment with speech is a paid ASR call). */
describe('useWakeWord 成本控制', () => {
  beforeEach(() => { vi.resetModules(); localStorage.clear() })

  /** 装好桩与真实 store；`wakeCheck` 由调用方注入以便断言探测调用次数。
   *  Wire the stubs and the real store; the caller injects `wakeCheck` so the probe
   *  call count can be asserted. */
  async function setup(wakeCheck: any, wakeDetect?: any) {
    vi.doMock('../../../api', () => ({
      api: {
        wakeCheck,
        wakeDetect: wakeDetect ?? vi.fn(async () => ({ ok: true, matched: false, command: '', text: '' })),
        transcribe: vi.fn(async () => ({ ok: true, text: '你好' })),
      },
    }))
    vi.doMock('../useChat', () => ({ sendText: vi.fn(), sendAnswer: vi.fn(), runTurn: vi.fn() }))
    vi.doMock('../useTts', () => ({ speaking: { value: false }, speakAuto: vi.fn(), stopSpeak: vi.fn() }))
    const store = await import('../store')
    const mod = await import('../useWakeWord')
    return { mod, store, api: { wakeCheck, wakeDetect } }
  }

  /** 两段之间的间隔小于 upload_throttle_ms → 第二段不探测。
   *  Two segments closer than upload_throttle_ms → only one probe. */
  it('节流：间隔小于 upload_throttle_ms 的连续段只上传一次', async () => {
    const { mod, store, api } = await setup(
      vi.fn(async () => ({ ok: true, hit: false, bypass: false })),   // 未命中：不触发后台提取，计数干净
    )
    store.vadConfig.upload_throttle_ms = 500

    await mod.handleSegment(new Blob(['x']))
    await mod.handleSegment(new Blob(['x']))

    expect(api.wakeCheck).toHaveBeenCalledTimes(1)
  })

  /** 连续失败达阈值 → 停探测并明确提示（spec「错误与降级」：不静默失败）。
   *  Three consecutive failures stop probing with a visible warning. */
  it('熔断：连续 3 次失败后停止上传并提示', async () => {
    const { mod, store, api } = await setup(vi.fn(async () => ({ ok: false })))
    store.vadConfig.upload_throttle_ms = 0   // 关掉节流，单独验熔断。Throttle off so only the breaker is under test.

    for (let i = 0; i < 5; i++) await mod.handleSegment(new Blob(['x']))

    expect(api.wakeCheck).toHaveBeenCalledTimes(3)
    expect(store.statusLine.value).toContain('云端唤醒暂不可用')
    // 提示写明两条出路：自动恢复 + 手动关开。
    // The warning names two ways out: auto-recovery and off/on.
    expect(store.statusLine.value).toContain('1 分钟后自动重试')
    expect(store.statusLine.value).toContain('关闭再开启')
  })
})

/**
 * 熔断的**出口**：熔断只有在「有人成功」时才解除，而一旦熔断就再没有任何上传 —— 成功永远不可能。
 * 计数器因此锁死，界面停在「聆听中」，唯一出路是刷新页面。
 *
 * 提示文案写明了出路，出路就必须真的存在：这里钉住「关闭再开启唤醒」真的清零计数、上传恢复，
 * 且**不需要刷新页面**。修好之前这条会红（关掉再打开后 wakeDetect 仍是 3 次调用，第 4 次被
 * 熔断挡掉）——「提示给的出路是假的」正是本重构要消灭的那类假保障。
 *
 * The breaker's **way out**. It only lifted on success, but once tripped nothing ever uploaded, so
 * success was impossible: the counter latched, the UI stayed on "listening", and a page reload was
 * the only escape. The warning names a way out, so that way out must exist: this pins that
 * "switch wake off and on" really clears the counter and restores uploads, **without a page
 * reload**. It fails before the fix (after the toggle, wakeDetect is still at 3 calls — the 4th is
 * blocked by the breaker), and a warning whose promised route does nothing is exactly the class of
 * false assurance this rework removes.
 */
describe('useWakeWord 熔断恢复', () => {
  beforeEach(() => { vi.resetModules(); localStorage.clear() })

  /** 熔断后关闭再开启 → 计数清零、探测恢复。Recovery via off/on clears the counter and resumes probes. */
  it('熔断后关闭再开启 → 计数清零且上传恢复（无需刷新页面）', async () => {
    const { ww, store } = await setupWake()
    const { api } = await import('../../../api')
    store.vadConfig.upload_throttle_ms = 0   // 关掉节流，单独验熔断。Throttle off so only the breaker is under test.

    await ww.toggleWake()                    // 开启监听。Enable listening.
    for (let i = 0; i < 3; i++) await ww.handleSegment(new Blob(['x']))

    expect(vi.mocked(api.wakeCheck)).toHaveBeenCalledTimes(3)
    expect(store.statusLine.value).toContain('云端唤醒暂不可用')
    // 提示写明的出路必须与实现一致：文案说「关闭再开启唤醒可立即恢复」。
    // The route named in the warning must match the implementation: it says off/on retries.
    expect(store.statusLine.value).toContain('关闭再开启')

    await ww.toggleWake()                    // 用户关闭。Switch off.
    await ww.toggleWake()                    // 再开启 —— 恢复动作。Switch on again: the recovery.
    await ww.handleSegment(new Blob(['x']))

    expect(vi.mocked(api.wakeCheck)).toHaveBeenCalledTimes(4)   // 真的又探测了。Genuinely probing again.
  })

  /** 冷静期结束后自动恢复试探 —— 断连是间歇性的，不能要求用户手动关开。
   *  Auto-probe after the cooldown: disconnects are intermittent, so recovery must not
   *  require a manual off/on. */
  it('熔断冷静期（60s）结束后自动恢复上传', async () => {
    vi.useFakeTimers()
    try {
      const { ww, store } = await setupWake()
      const { api } = await import('../../../api')
      store.vadConfig.upload_throttle_ms = 0

      await ww.toggleWake()
      for (let i = 0; i < 3; i++) await ww.handleSegment(new Blob(['x']))
      expect(vi.mocked(api.wakeCheck)).toHaveBeenCalledTimes(3)

      // 冷静期内不上传。No uploads during the cooldown.
      await ww.handleSegment(new Blob(['x']))
      expect(vi.mocked(api.wakeCheck)).toHaveBeenCalledTimes(3)

      // 60s 后自动放行试探。A probe is allowed after 60s.
      await vi.advanceTimersByTimeAsync(61_000)
      await ww.handleSegment(new Blob(['x']))
      expect(vi.mocked(api.wakeCheck)).toHaveBeenCalledTimes(4)
    } finally {
      vi.useRealTimers()
    }
  })
})

/**
 * 状态反馈：`/voice/wake` 与 `/voice/transcribe` 都是**云端往返，要数秒**。这两个状态
 * （`transcribing` / `recording`）在本次重构后一度无人赋值 —— 旧实现由 Vosk 回调驱动，spec 说
 * 状态机不变、只换触发源，故按「谁在等云端」补回。没有它们，界面在整段往返里停在「聆听中」，
 * 用户以为没听见、重说一遍，反而多一次付费上传。
 *
 * State feedback: both endpoints are **cloud round-trips that take seconds**. `transcribing` and
 * `recording` briefly had no assignments after the rework (the old code drove them from the Vosk
 * callbacks); the spec says the state machine is unchanged with only the trigger swapped, so they
 * are restored around "whoever is waiting on the cloud". Without them the UI sits on "listening"
 * through the whole round-trip, the user thinks they were not heard, repeats themselves, and buys
 * another paid upload.
 */
describe('useWakeWord 状态反馈', () => {
  beforeEach(() => { vi.resetModules(); localStorage.clear() })

  /** 装好桩与真实 store；`wakeDetect` 由调用方注入以便控制解析时机。
   *  Wire the stubs and the real store; the caller injects `wakeDetect` to control when it resolves. */
  async function setup(wakeDetect: any, checkResp?: any) {
    vi.doMock('../../../api', () => ({
      api: {
        wakeCheck: vi.fn(async () => checkResp ?? { ok: true, hit: true, bypass: false }),
        wakeDetect,
        transcribe: vi.fn(async () => ({ ok: true, text: '你好' })),
      },
    }))
    vi.doMock('../useChat', () => ({ sendText: vi.fn(), sendAnswer: vi.fn(), runTurn: vi.fn() }))
    vi.doMock('../useTts', () => ({ speaking: { value: false }, speakAuto: vi.fn(), stopSpeak: vi.fn() }))
    const store = await import('../store')
    const mod = await import('../useWakeWord')
    store.vadConfig.upload_throttle_ms = 0
    return { store, mod }
  }

  /** cloud 模式（完整云端判定路径）：判定在途 → transcribing；返回未命中 → 回落到原状态。
   *  Cloud mode (full cloud-judging path): in-flight judgement → transcribing; a miss
   *  falls back to the prior state. (本地快检路径不设 transcribing —— 它毫秒级返回。) */
  it('云端判定期间进入 transcribing，返回后回落到原状态', async () => {
    let release!: (v: any) => void
    const wakeDetect = vi.fn(() => new Promise<any>((res) => { release = res }))
    const { store, mod } = await setup(wakeDetect)
    store.setWakeMode('cloud')                  // 走完整云端判定路径。Force the full cloud path.
    store.state.value = 'listening'

    const p = mod.handleSegment(new Blob(['x']))
    await Promise.resolve()
    expect(store.state.value).toBe('transcribing')   // 数秒的往返里界面不能一动不动。Not silent for seconds.

    release({ ok: true, matched: false, command: '', text: '今天天气怎么样。' })
    await p
    expect(store.state.value).toBe('listening')      // 未命中 → 回聆听。No match → back to listening.
  })

  /** plan:195 指定的那条：快检命中 → 立即 recording 等指令；窗口过期回聆听。
   *  A quick-check hit enters recording at once (no cloud wait); the window expiry returns to listening. */
  it('只命中唤醒词 → 进入 recording 等指令；窗口过期回聆听', async () => {
    vi.useFakeTimers()
    try {
      const { store, mod } = await setup(
        vi.fn(async () => ({ ok: true, matched: true, command: '', text: '衍衡。' })),
      )
      store.wakeEnabled.value = true              // 前提：聆听只在唤醒开着时才存在。Precondition: listening only exists while wake is on.
      store.state.value = 'listening'

      await mod.handleSegment(new Blob(['x']))
      expect(store.state.value).toBe('recording')    // 命中即动作，不等提取。Acts on the hit, not the extraction.

      await vi.advanceTimersByTimeAsync(8000)        // 命令窗口过期。The command window expires.
      expect(store.state.value).toBe('listening')    // 不能永久停在录音中。Never park on "recording".
    } finally { vi.useRealTimers() }
  })

  /** 说出指令后 → 转写期间 transcribing，指令发出后交回 useChat（thinking）。 */
  it('等指令期间说指令 → 转写中 → 交回一轮', async () => {
    let release!: (v: any) => void
    const transcribe = vi.fn(() => new Promise<any>((res) => { release = res }))
    const { store, mod } = await setup(
      vi.fn(async () => ({ ok: true, matched: true, command: '', text: '衍衡。' })),
    )
    const { api } = await import('../../../api')
    vi.mocked(api.transcribe).mockImplementation(transcribe as any)
    const { sendText } = await import('../useChat')
    store.state.value = 'listening'
    await mod.handleSegment(new Blob(['x']))         // 裸唤醒词 → recording。Bare wake word → recording.
    await new Promise((r) => setTimeout(r, 0))       // 后台提取 settle（无指令，窗口保持）。Extraction settles (no command, window stays).
    expect(store.state.value).toBe('recording')

    const p = mod.handleSegment(new Blob(['x']))     // 第二段 = 指令。Second segment is the command.
    await Promise.resolve()
    expect(store.state.value).toBe('transcribing')

    release({ ok: true, text: '帮我查天气' })
    await p
    expect(sendText).toHaveBeenCalledWith('帮我查天气')
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
  vi.doMock('../../../api', () => ({
    api: {
      // wakeCheck 桩返回失败：模拟探测持续失败（熔断计数的来源）。
      // The wakeCheck stub fails: simulated probe failures (what the breaker counts).
      wakeCheck: vi.fn(async () => ({ ok: false })),
      wakeDetect: vi.fn(async () => ({ ok: true, matched: false, command: '', text: '' })),
      transcribe: vi.fn(async () => ({ ok: true, text: '' })),
    },
  }))
  vi.doMock('../useChat', () => ({ sendText: vi.fn(), sendAnswer: vi.fn(), runTurn: vi.fn() }))
  vi.doMock('../useTts', async () => {
    const { ref } = await import('vue')
    return { speaking: ref(false), speakAuto: vi.fn(), stopSpeak: vi.fn() }
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
  async function setupWait(opts: { wake?: any; check?: any; sent?: string[] } = {}) {
    const sent = opts.sent ?? []
    vi.doMock('../../../api', () => ({
      api: {
        wakeCheck: opts.check ?? vi.fn(async () => ({ ok: true, hit: true, bypass: false })),
        wakeDetect: opts.wake ?? vi.fn(async () => ({ ok: true, matched: false, command: '', text: '' })),
        transcribe: vi.fn(async () => ({ ok: true, text: '允许本次' })),
      },
    }))
    vi.doMock('../useChat', () => ({
      sendText: (t: string) => { sent.push(t) },
      sendAnswer: vi.fn(),
      runTurn: vi.fn(),
    }))
    vi.doMock('../useTts', () => ({ speaking: { value: false }, speakAuto: vi.fn(), stopSpeak: vi.fn() }))
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
      expect(sendAnswer).toHaveBeenCalledWith(
        '', 'yes', 'voice', expect.objectContaining({ text: '确认执行吗？' }),
      )
    } finally { vi.useRealTimers() }
  })

  /** 只说了唤醒词、没说指令 → 窗口过后，无关语音**不得**被当成指令执行。
   *  A bare wake word with no command: after the window expires, unrelated speech must
   *  not be executed as a command. */
  it('等指令过期 → 之后的无关语音不被当成指令执行', async () => {
    vi.useFakeTimers()
    try {
      const sent: string[] = []
      const check = vi.fn()
        .mockResolvedValueOnce({ ok: true, hit: true, bypass: false })   // 第一段：命中（裸唤醒词）
        .mockResolvedValue({ ok: true, hit: false, bypass: false })      // 之后：无关语音，快检未命中
      const wakeDetect = vi.fn()
        .mockResolvedValue({ ok: true, matched: true, command: '', text: '衍衡。' })   // 提取无指令 → 窗口保持
      const { store, mod } = await setupWait({ check, wake: wakeDetect, sent })

      await mod.handleSegment(new Blob(['x']))    // 裸唤醒词 → 进等指令窗口。Bare wake word → command window opens.
      await vi.advanceTimersByTimeAsync(0)        // 后台提取 settle（无指令）。Background extraction settles (no command).
      expect(sent).toEqual([])

      await vi.advanceTimersByTimeAsync(8000)     // 窗口过期。The window expires.
      await mod.handleSegment(new Blob(['x']))    // 之后的无关语音。A later unrelated segment.
      await vi.advanceTimersByTimeAsync(0)

      expect(sent).toEqual([])                   // 不得被执行。Must not be executed.
      expect(check).toHaveBeenCalledTimes(2)     // 回到正常唤醒判定。Back to normal wake detection.
      expect(store.statusLine.value).not.toContain('请说指令')
    } finally { vi.useRealTimers() }
  })

  /** 一轮结束（done/error）3 秒后回聆听，界面不会永久停在「完成」。
   *  续聊窗口关闭（followup_window_ms=0）时保持旧语义。 */
  it('窗口关闭：一轮结束 3 秒后回到聆听（旧行为）', async () => {
    vi.useFakeTimers()
    try {
      const { store } = await setupWait()
      store.wakeEnabled.value = true
      store.vadConfig.followup_window_ms = 0
      store.state.value = 'done'
      await nextTick()
      expect(store.state.value).toBe('done')      // 3 秒内不动。Unchanged within three seconds.

      await vi.advanceTimersByTimeAsync(3000)
      expect(store.state.value).toBe('listening')
    } finally { vi.useRealTimers() }
  })
})

/** 续聊窗口（docs/designs/03-A）：回合结束 → followup 态，窗口内段免唤醒直接成指令，
 *  到期回聆听；说唤醒词照常进指令窗（窗口与唤醒语义兼容）。
 *
 *  Follow-up window (docs/designs/03-A): turn end → followup; segments inside become
 *  wake-free instructions; expiry returns to listening; the wake word still opens the
 *  command window as usual (window and wake semantics stay compatible). */
describe('useWakeWord 续聊窗口', () => {
  beforeEach(() => { vi.resetModules(); localStorage.clear() })

  async function setupFw(opts: { transcribe?: any; sent?: string[] } = {}) {
    const sent = opts.sent ?? []
    vi.doMock('../../../api', () => ({
      api: {
        wakeCheck: vi.fn(async () => ({ ok: true, hit: false, bypass: false })),
        wakeDetect: vi.fn(async () => ({ ok: true, matched: false })),
        transcribe: opts.transcribe ?? vi.fn(async () => ({ ok: true, text: '接着查一下气温' })),
      },
    }))
    vi.doMock('../useChat', () => ({
      sendText: (t: string) => { sent.push(t) },
      sendAnswer: vi.fn(),
      runTurn: vi.fn(),
    }))
    // speaking 必须是真 ref：播报门控与窗口重武装的 watch 都挂在它上面。
    // speaking must be a real ref: the playback gate and window re-arm watches hang on it.
    const { ref } = await import('vue')
    const speaking = ref(false)
    vi.doMock('../useTts', () => ({ speaking, speakAuto: vi.fn(), stopSpeak: vi.fn() }))
    const store = await import('../store')
    const mod = await import('../useWakeWord')
    store.vadConfig.upload_throttle_ms = 0
    store.vadConfig.followup_window_ms = 6000
    return { store, mod, sent, speaking }
  }

  /** 回合结束 → 立即进 followup；到期回聆听。
   *  Turn end → followup immediately; expiry → listening. */
  it('done → followup → 到期 listening', async () => {
    vi.useFakeTimers()
    try {
      const { store } = await setupFw()
      store.wakeEnabled.value = true
      store.state.value = 'done'
      await nextTick()
      expect(store.state.value).toBe('followup')

      await vi.advanceTimersByTimeAsync(5999)
      expect(store.state.value).toBe('followup')   // 窗口未到。Inside the window.
      await vi.advanceTimersByTimeAsync(2)
      expect(store.state.value).toBe('listening')
    } finally { vi.useRealTimers() }
  })

  /** 窗口内的段免唤醒直接成为新指令（不走快检/熔断/节流）。
   *  A segment inside the window becomes a fresh instruction without the wake word. */
  it('窗口内段 → 转写后直接 sendText（免唤醒）', async () => {
    vi.useFakeTimers()
    try {
      const { store, mod, sent } = await setupFw()
      store.wakeEnabled.value = true
      store.state.value = 'done'
      await nextTick()
      expect(store.state.value).toBe('followup')

      await mod.handleSegment(new Blob(['x']))
      expect(sent).toEqual(['接着查一下气温'])
      store.state.value = 'thinking'   // sendText 的 mock 不改状态，模拟 runTurn 接管。
    } finally { vi.useRealTimers() }
  })

  /** 窗口内说唤醒词 → 照常进指令窗（裸唤醒词不整句当指令发出去）。
   *  A bare wake word inside the window opens the command window as usual (it is not
   *  sent verbatim as an instruction). */
  it('窗口内说唤醒词 → 进指令窗', async () => {
    vi.useFakeTimers()
    try {
      const sent: string[] = []
      const transcribe = vi.fn(async () => ({ ok: true, text: '衍衡' }))
      const { store, mod } = await setupFw({ transcribe, sent })
      store.wakeEnabled.value = true
      store.state.value = 'done'
      await nextTick()
      expect(store.state.value).toBe('followup')

      await mod.handleSegment(new Blob(['x']))
      expect(sent).toEqual([])                      // 裸唤醒词不发指令。A bare wake fires no command.
      expect(store.statusLine.value).toContain('请说指令')
      expect(store.state.value).toBe('recording')
    } finally { vi.useRealTimers() }
  })

  /** 播报结束重新计满窗口（窗口 = 播报完后的 N 毫秒）。
   *  End-of-playback re-arms a full window (the window is N ms after playback ends). */
  it('播报结束重新武装窗口', async () => {
    vi.useFakeTimers()
    try {
      const { store, speaking } = await setupFw()
      store.wakeEnabled.value = true
      store.state.value = 'done'
      await nextTick()
      expect(store.state.value).toBe('followup')
      await vi.advanceTimersByTimeAsync(5000)       // 窗口过半。Halfway.
      speaking.value = true
      await nextTick()
      speaking.value = false
      await nextTick()
      await vi.advanceTimersByTimeAsync(5500)       // 重新计满后仍在窗内。Re-armed: still inside.
      expect(store.state.value).toBe('followup')
      await vi.advanceTimersByTimeAsync(1000)
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

/** barge-in 打断播报（docs/designs/02 批3）：vad.barge_in 开 → 播报期间起能量监控，
 *  命中即 stopSpeak('barge_in')；默认关 → 行为与旧版全同（不起监控）。
 *
 *  Barge-in (docs/designs/02 batch 3): with vad.barge_in on, playback starts an energy
 *  monitor that calls stopSpeak('barge_in') on a hit; off by default → legacy behaviour
 *  (no monitor). */
describe('useWakeWord barge-in 打断播报', () => {
  beforeEach(() => { vi.resetModules(); localStorage.clear() })

  async function setup(opts: { bargeIn: boolean }) {
    vi.doMock('../../../api', () => ({
      api: {
        wakeCheck: vi.fn(async () => ({ ok: true, hit: false, bypass: false })),
        wakeDetect: vi.fn(async () => ({ ok: true, matched: false })),
        transcribe: vi.fn(async () => ({ ok: true, text: '' })),
      },
    }))
    vi.doMock('../useChat', () => ({ sendText: vi.fn(), sendAnswer: vi.fn(), runTurn: vi.fn() }))
    const { ref } = await import('vue')
    const speaking = ref(false)
    const stopSpeak = vi.fn()
    vi.doMock('../useTts', () => ({ speaking, speakAuto: vi.fn(), stopSpeak }))
    const startBargeInMonitor = vi.fn(() => ({ stop: vi.fn() }))
    vi.doMock('../bargeIn', () => ({ startBargeInMonitor, BARGE_IN_DURATION_MS: 400 }))
    const store = await import('../store')
    store.vadConfig.barge_in = opts.bargeIn
    await import('../useWakeWord')
    return { speaking, stopSpeak, startBargeInMonitor }
  }

  /** 开启时：播报 → 起监控；命中 → 掐断播报。On: playback starts the monitor; a hit
   *  cuts the playback. */
  it('barge_in 开 → 播报起监控，命中调 stopSpeak', async () => {
    const { speaking, stopSpeak, startBargeInMonitor } = await setup({ bargeIn: true })
    speaking.value = true
    await nextTick()
    expect(startBargeInMonitor).toHaveBeenCalledTimes(1)
    const cfg = startBargeInMonitor.mock.calls[0][0] as any
    expect(cfg.durationMs).toBe(400)
    cfg.onTrigger()
    expect(stopSpeak).toHaveBeenCalledWith('barge_in')
  })

  /** 默认关：不起监控（旧版「播报期间停麦」行为原样保留）。
   *  Default off: no monitor starts (legacy "mic off while speaking" preserved). */
  it('barge_in 关 → 不起监控', async () => {
    const { speaking, stopSpeak, startBargeInMonitor } = await setup({ bargeIn: false })
    speaking.value = true
    await nextTick()
    expect(startBargeInMonitor).not.toHaveBeenCalled()
    expect(stopSpeak).not.toHaveBeenCalled()
  })

  /** 播报结束（含被打断）→ 监控被收掉（独立流不得泄漏）。
   *  Playback ends (incl. interrupted) → the monitor is released (no leaked stream). */
  it('播报结束收掉监控', async () => {
    const { speaking, startBargeInMonitor } = await setup({ bargeIn: true })
    speaking.value = true
    await nextTick()
    const handle = (startBargeInMonitor.mock.results[0].value as { stop: ReturnType<typeof vi.fn> })
    speaking.value = false
    await nextTick()
    expect(handle.stop).toHaveBeenCalledTimes(1)
  })
})
