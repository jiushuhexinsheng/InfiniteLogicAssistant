import { beforeEach, describe, expect, it, vi } from 'vitest'

// 只桩掉网络层，保留 store 真实实现（断言写入的消息）。
// Stub only the network layer, keeping the real store (to assert on the written message).
vi.mock('../../../api', () => ({
  api: { answer: vi.fn(), callTool: vi.fn(), forkSession: vi.fn(), stopTask: vi.fn() },
  streamUtter: vi.fn(),
}))
// runTurn 会调用 speakAuto（TTS）；此处桩掉以免依赖浏览器语音 API。
// runTurn calls speakAuto (TTS); stub it out so no browser speech API is needed.
vi.mock('../useTts', async () => {
  const { ref } = await import('vue')
  return { speakAuto: vi.fn(), stopSpeak: vi.fn(), speaking: ref(false) }
})

import { api, streamUtter } from '../../../api'
import { currentSessionId, messages, pendingQuestion, state, tokenUsage } from '../store'
import { makeBlock } from '../../../blocks/normalize'
import { runTurn, sendAnswer, sendText, outboxCount, clearQueued, forkAt, sendEdited, regenerate } from '../useChat'

/** useChat 回答投递的错误文案。Error text for useChat's answer delivery. */
describe('useChat sendAnswer 错误处理', () => {
  beforeEach(() => {
    messages.value = []
    currentSessionId.value = ''
    vi.mocked(api.answer).mockReset()
  })

  /** 失败写入系统消息：文案统一走 formatError，标点为全角。 */
  it('回答投递失败时写入统一格式的系统消息', async () => {
    currentSessionId.value = 's1'
    vi.mocked(api.answer).mockRejectedValue(new Error('连接被重置'))
    await sendAnswer('是的')
    const last = messages.value[messages.value.length - 1]
    expect(last?.role).toBe('system')
    expect(last?.text).toBe('回答投递失败：连接被重置')
  })

  /** 非 Error 的拒绝原因不应渲染成空串。 */
  it('非 Error 拒绝原因回退为「未知错误」而非空串', async () => {
    currentSessionId.value = 's1'
    vi.mocked(api.answer).mockRejectedValue(null)
    await sendAnswer('是的')
    expect(messages.value[messages.value.length - 1]?.text).toBe('回答投递失败：未知错误')
  })

  /** 成功时不写入错误消息（正常会写入回答记录，但那不是错误消息）。
   *  No error message on success — the answer record itself is written, but that is not an error. */
  it('投递成功时不写入错误消息', async () => {
    currentSessionId.value = 's1'
    vi.mocked(api.answer).mockResolvedValue({ ok: true })
    await sendAnswer('是的')
    expect(messages.value.some((m) => m.role === 'system' || m.text.includes('失败'))).toBe(false)
  })

  /** 结构化确认：空文本 + choice 也应投递（按钮回答不带文本）。
   *  api.answer 现在携带 source/qid（作答通道可审计、问答配对）。 */
  it('结构化确认允许空文本并透传 choice', async () => {
    currentSessionId.value = 's1'
    vi.mocked(api.answer).mockResolvedValue({ ok: true })
    await sendAnswer('', 'yes')
    expect(api.answer).toHaveBeenCalledWith('s1', '', 'yes', expect.objectContaining({ source: 'typed' }))
  })

  /** 既无文本也无 choice 时不投递（避免空回答解除后端阻塞）。 */
  it('既无文本也无 choice 时不投递', async () => {
    currentSessionId.value = 's1'
    await sendAnswer('   ')
    expect(api.answer).not.toHaveBeenCalled()
  })

  /** 任意字符串 choice 都能透传（权限策略的 once / always 等）。 */
  it('任意字符串 choice 均可透传', async () => {
    currentSessionId.value = 's1'
    vi.mocked(api.answer).mockResolvedValue({ ok: true })
    await sendAnswer('', 'always')
    expect(api.answer).toHaveBeenCalledWith('s1', '', 'always', expect.objectContaining({ source: 'typed' }))
  })
})

/** 问答进入聊天记录（需求 6）。Questions and answers enter the chat record. */
describe('useChat 问答入聊天记录', () => {
  beforeEach(() => {
    messages.value = []
    currentSessionId.value = ''
    pendingQuestion.value = null
    vi.mocked(api.answer).mockReset()
    vi.mocked(api.answer).mockResolvedValue({ ok: true })
    vi.mocked(streamUtter).mockReset()
  })

  /** 提问以 question 块入记录（块协议：不再拼 ❓ 前缀文本，投影供旧读取方）。
   *  模拟真实分发顺序：onEvent 先于 onQuestion。 */
  it('提问以 question 块入聊天记录', async () => {
    vi.mocked(streamUtter).mockImplementation(async (_t: string, h: any) => {
      const evt = { type: 'question', question: '确认执行吗？', session_id: 's1', kind: 'choice',
                    options: [{ value: 'yes', label: '确认' }], qid: 'q_1' }
      h.onEvent?.(evt)
      h.onQuestion?.({ question: '确认执行吗？', session_id: 's1', kind: 'choice',
                       options: [{ value: 'yes', label: '确认' }], qid: 'q_1' })
      return 's1'
    })
    messages.value = [{ id: 'm1', role: 'user', text: '做事', blocks: [], timestamp: Date.now() }]
    await runTurn()
    const q = messages.value.find((m) => m.role === 'assistant')
    const qBlock = q?.blocks?.find((b) => b.type === 'question')
    expect(qBlock?.payload.question).toBe('确认执行吗？')
    expect(qBlock?.payload.qid).toBe('q_1')
    // 文本投影保留 ❓ 形态（旧读取方/摘要消费）
    expect(q?.text).toContain('确认执行吗？')
  })

  /** 选择类回答：以被选 option 的 label 入记录（不写机器值）。 */
  it('选择类回答以 label 入聊天记录', async () => {
    currentSessionId.value = 's1'
    pendingQuestion.value = {
      text: '确认执行吗？', kind: 'choice',
      options: [{ value: 'yes', label: '确认' }, { value: 'no', label: '取消' }],
    }
    await sendAnswer('', 'yes')
    const last = messages.value[messages.value.length - 1]
    expect(last?.role).toBe('user')
    expect(last?.text).toBe('确认')
  })

  /** 文本类回答：以输入文本入记录。 */
  it('文本类回答以输入文本入聊天记录', async () => {
    currentSessionId.value = 's1'
    pendingQuestion.value = { text: '目标位置？', kind: 'text', options: [] }
    await sendAnswer('桌面')
    const last = messages.value[messages.value.length - 1]
    expect(last?.role).toBe('user')
    expect(last?.text).toBe('桌面')
  })

  /** 回归（截图 bug #1 修复）：问题块在消息里（带 qid）→ 作答贴进**问题所在卡片**、
   *  紧跟问题块之后，不再生成独立用户气泡。
   *  此前作答恒落尾部用户消息：问答被卡片边界拆散，且卡片后续事件（09:40 的
   *  「执行失败」）渲染在 09:39 作答气泡之上 —— 视觉时序倒置。
   *
   *  Regression (screenshot bug #1 fix): when the question block lives in a message
   *  (with a qid), the answer attaches INSIDE that card right after the question —
   *  no detached user bubble. Previously answers always became trailing user
   *  messages, splitting Q from A and inverting the visual order against later card
   *  events. */
  it('有配对问题时作答入问题所在卡片、不新增用户消息', async () => {
    currentSessionId.value = 's1'
    const q = makeBlock('question', {
      qid: 'q_1', question: '目标位置？', kind: 'text', options: [], status: 'pending',
    })
    messages.value = [
      { id: 'm1', role: 'user', text: '做事', blocks: [], timestamp: Date.now() },
      { id: 'm2', role: 'assistant', text: '', blocks: [q], timestamp: Date.now() },
    ]
    pendingQuestion.value = { text: '目标位置？', kind: 'text', options: [], qid: 'q_1' }
    await sendAnswer('桌面')
    expect(messages.value).toHaveLength(2)            // 不新增用户消息
    const blocks = messages.value[1].blocks!
    expect(blocks.map((b) => b.type)).toEqual(['question', 'answer'])
    expect(blocks[0].payload.status).toBe('answered')
    expect(blocks[1].payload).toMatchObject({ qid: 'q_1', text: '桌面', source: 'typed' })
    expect(pendingQuestion.value).toBeNull()
  })

  /** 投递失败时不写回答记录（避免记录与后端状态不一致）。 */
  it('投递失败时不写回答记录', async () => {
    currentSessionId.value = 's1'
    pendingQuestion.value = { text: '目标位置？', kind: 'text', options: [] }
    vi.mocked(api.answer).mockRejectedValue(new Error('会话已失效'))
    await sendAnswer('桌面')
    expect(messages.value.some((m) => m.text === '桌面')).toBe(false)
  })

  /** 语音作答快照绑定（修「回答和问题分开」）：云端转写要等数秒，期间 pendingQuestion
   *  可能被清（流错误/中止/切会话）—— 作答必须绑定段落捕获时的问题快照：qid 照常投递、
   *  答案照常贴进问题卡，不得因 store 已空而走独立用户气泡兜底（那正是「问答分开」）。
   *
   *  Voice-answer snapshot binding (fixes "the answer and the question are split
   *  apart"): cloud ASR takes seconds, and pendingQuestion may be cleared meanwhile
   *  (stream error / abort / session switch). The answer must bind to the question
   *  snapshot captured when the segment started: the qid is still delivered and the
   *  answer still attaches inside the question's card — an empty store must not send
   *  it down the standalone-user-bubble fallback (which is exactly the Q/A split). */
  it('携带问题快照时即使 pendingQuestion 已清也投递 qid 并贴块', async () => {
    currentSessionId.value = 's1'
    const q = makeBlock('question', {
      qid: 'q_1', question: '目标位置？', kind: 'text', options: [], status: 'pending',
    })
    messages.value = [
      { id: 'm1', role: 'user', text: '做事', blocks: [], timestamp: Date.now() },
      { id: 'm2', role: 'assistant', text: '', blocks: [q], timestamp: Date.now() },
    ]
    // 段落捕获快照之后、转写期间流错误清空了 pendingQuestion（read-after-await 竞态）。
    // Between snapshot capture and ASR completion, a stream error cleared pendingQuestion.
    pendingQuestion.value = null
    await sendAnswer('桌面', undefined, 'voice', {
      text: '目标位置？', kind: 'text', options: [], qid: 'q_1',
    })
    expect(api.answer).toHaveBeenCalledWith(
      's1', '桌面', undefined, expect.objectContaining({ qid: 'q_1', source: 'voice' }),
    )
    expect(messages.value).toHaveLength(2)            // 不新增用户消息（不分开）
    const blocks = messages.value[1].blocks!
    expect(blocks.map((b) => b.type)).toEqual(['question', 'answer'])
    expect(blocks[1].payload).toMatchObject({ qid: 'q_1', text: '桌面', source: 'voice' })
    expect(pendingQuestion.value).toBeNull()
  })
})

/** 消息排队与作答转发（docs/designs/06 批3）：回合中再发入队、收束连发、
 *  取消词立即中止清队、待答问题转作答语义。
 *
 *  Message queue and answer forwarding (docs/designs/06 batch 3): sending during a
 *  turn queues, turn end chains, cancel words abort and clear, a pending question
 *  becomes an answer. */
describe('useChat 消息排队', () => {
  beforeEach(() => {
    messages.value = []
    currentSessionId.value = ''
    pendingQuestion.value = null
    state.value = 'idle'
    clearQueued()
    vi.mocked(api.answer).mockReset()
    vi.mocked(api.answer).mockResolvedValue({ ok: true })
    vi.mocked(streamUtter).mockReset()
    // 默认挂起的流：只记录 handlers 供测试手动触发收束。
    // A hanging stream by default: only records handlers for the test to finish manually.
    vi.mocked(streamUtter).mockImplementation(async (_t: string, h: any) => {
      ;(streamUtter as any).__lastHandlers = h
      return 's1'
    })
  })

  /** 回合进行中发送 → 入队不落消息；onDone 收束 → 自动连发。 */
  it('回合中入队，收束后自动连发', async () => {
    sendText('第一条')                     // idle → 直接起一轮。Idle → start a turn.
    expect(messages.value.filter(m => m.role === 'user')).toHaveLength(1)
    expect(state.value).toBe('thinking')

    sendText('第二条')                     // 回合中 → 入队。Turn running → queued.
    expect(outboxCount.value).toBe(1)
    expect(messages.value.filter(m => m.role === 'user')).toHaveLength(1)

    ;(streamUtter as any).__lastHandlers.onDone('s1')   // 收束 → 弹队。Wrap up → flush.
    await Promise.resolve()
    expect(outboxCount.value).toBe(0)
    const users = messages.value.filter(m => m.role === 'user')
    expect(users).toHaveLength(2)
    expect(users[1].text).toBe('第二条')   // 连发的是排队消息本身。The queued message itself is chained.
  })

  /** 取消词立即中止并清队（排队不得吞掉取消）。 */
  it('取消词清队并中止', async () => {
    sendText('第一条')
    sendText('第二条')                      // 排队。Queued.
    expect(outboxCount.value).toBe(1)

    sendText('停止')
    expect(outboxCount.value).toBe(0)        // 队列清空。Queue cleared.
    expect(messages.value.filter(m => m.role === 'user')).toHaveLength(1)  // 不新增消息。No new message.
  })

  /** 回归靶子（实测 bug）：唤醒指令落在 listening 态、续聊接话落在 followup 态 ——
   *  这些语音链状态必须**直接发送**，不得入队（没有在跑的回合会去弹队，入队即永久卡死）。
   *
   *  Regression target (field bug): wake commands land in listening, follow-up
   *  replies in followup — these voice-chain states must send immediately, never
   *  queue (no live turn exists to flush a queued message, so queueing wedges it
   *  forever). */
  it.each(['listening', 'followup', 'recording', 'transcribing', 'standby'] as const)(
    '语音链状态 %s 直接发送不入队',
    async (st) => {
      state.value = st
      sendText('你好')
      expect(outboxCount.value).toBe(0)
      expect(streamUtter).toHaveBeenCalledTimes(1)
      expect(messages.value.filter(m => m.role === 'user')).toHaveLength(1)
      expect(messages.value[messages.value.length - 1].text).toBe('你好')
    },
  )

  /** 对照：真正的回合状态（thinking/tool_calling/responding）才入队。 */
  it.each(['thinking', 'tool_calling', 'responding'] as const)(
    '回合状态 %s 入队等待收束',
    async (st) => {
      state.value = st
      sendText('你好')
      expect(outboxCount.value).toBe(1)
      expect(streamUtter).not.toHaveBeenCalled()
      clearQueued()
    },
  )

  /** 待答问题时发送 → 转作答语义（选项精确匹配成结构化 choice），不排队。 */
  it('待答时发送转作答（选项命中 → choice）', async () => {
    currentSessionId.value = 's1'
    state.value = 'thinking'                 // 即便回合在跑，作答也优先。Answer wins even mid-turn.
    pendingQuestion.value = {
      text: '确认执行吗？', kind: 'choice',
      options: [{ value: 'yes', label: '允许本次' }, { value: 'no', label: '拒绝' }],
    }

    sendText('允许本次')
    await new Promise(r => setTimeout(r, 0))
    expect(api.answer).toHaveBeenCalledWith('s1', '', 'yes', expect.objectContaining({ source: 'typed' }))
    expect(outboxCount.value).toBe(0)        // 不排队。Not queued.
    expect(streamUtter).not.toHaveBeenCalled()  // 不新开回合。No new turn.
    // 记录形态是 answer 块（作答），不是普通话语消息。Recorded as an answer block, not an utterance.
    const um = messages.value.filter(m => m.role === 'user')
    expect(um).toHaveLength(1)
    expect(um[0].blocks?.[0]?.type).toBe('answer')
  })
})

/** 分叉 / 编辑重发 / 重新生成（docs/designs/07）。Fork / edit-resend / regenerate. */
describe('useChat 分叉与编辑', () => {
  beforeEach(() => {
    messages.value = []
    currentSessionId.value = 's1'
    pendingQuestion.value = null
    state.value = 'done'
    tokenUsage.value = {}
    clearQueued()
    vi.mocked(api.answer).mockReset()
    vi.mocked(api.forkSession).mockReset()
    vi.mocked(streamUtter).mockReset()
    vi.mocked(streamUtter).mockImplementation(async () => 's1')
  })

  const mkMsg = (role: 'user' | 'assistant', text: string) =>
    ({ id: role + text, role, text, blocks: [], timestamp: Date.now() }) as any

  /** forkAt：服务端 fork 成功 → 本地截断 + 切换会话 id + 清待答/用量。
   *  Success → local truncation + session id switch + pending/usage reset. */
  it('forkAt 截断前缀并切到新会话', async () => {
    messages.value = [mkMsg('user', 'a'), mkMsg('assistant', 'b'), mkMsg('user', 'c')]
    vi.mocked(api.forkSession).mockResolvedValue({ ok: true, session: { id: 's2' } as any })

    const ok = await forkAt(1)
    expect(ok).toBe(true)
    expect(api.forkSession).toHaveBeenCalledWith('s1', 1)
    expect(currentSessionId.value).toBe('s2')
    expect(messages.value.map(m => m.text)).toEqual(['a', 'b'])
  })

  /** 服务端拒绝（如 409）→ 本地不动。Server refusal (409 etc.) leaves local state alone. */
  it('forkAt 失败不改本地状态', async () => {
    messages.value = [mkMsg('user', 'a'), mkMsg('assistant', 'b')]
    vi.mocked(api.forkSession).mockRejectedValue(new Error('会话正在等待回答，无法分叉'))

    const ok = await forkAt(0)
    expect(ok).toBe(false)
    expect(currentSessionId.value).toBe('s1')
    // 原消息不动；失败追加系统消息（可感知）。Original messages untouched; a system message surfaces the failure.
    expect(messages.value.filter(m => m.role !== 'system')).toHaveLength(2)
    expect(messages.value.some(m => m.role === 'system' && m.text.includes('分叉失败'))).toBe(true)
  })

  /** 末条编辑：不调 fork，直接改写重发起一轮。
   *  Tail edit: no fork call, rewrite in place and start a turn. */
  it('sendEdited 末条直接改写重发', async () => {
    messages.value = [mkMsg('user', '旧问题'), mkMsg('assistant', '回答'), mkMsg('user', '末条')]
    vi.mocked(api.forkSession).mockResolvedValue({ ok: true, session: { id: 's2' } as any })

    const ok = await sendEdited(2, '新末条')
    expect(ok).toBe(true)
    expect(api.forkSession).not.toHaveBeenCalled()
    expect(messages.value[2].text).toBe('新末条')
    expect(messages.value[2].blocks?.[0]?.payload).toMatchObject({ md: '新末条' })
    expect(streamUtter).toHaveBeenCalledTimes(1)   // 已起新一轮。A new turn started.
  })

  /** 非末条编辑：必须先 fork（整段覆盖存储下保原路径），再改写重发。
   *  Non-tail edit must fork first (whole-overwrite storage: keep the original path). */
  it('sendEdited 非末条先分叉', async () => {
    messages.value = [mkMsg('user', '第一问'), mkMsg('assistant', '第一答'), mkMsg('user', '第二问')]
    vi.mocked(api.forkSession).mockResolvedValue({ ok: true, session: { id: 's2' } as any })

    const ok = await sendEdited(0, '改写的第一问')
    expect(ok).toBe(true)
    expect(api.forkSession).toHaveBeenCalledWith('s1', 0)
    expect(currentSessionId.value).toBe('s2')
    // 用户消息截断到被编辑那条（其后可能有 runTurn 的空 assistant 占位，属 mock 无事件的产物）。
    // User messages truncate at the edited one (a trailing empty assistant placeholder may
    // follow — an artifact of runTurn under an event-less mock).
    expect(messages.value.filter(m => m.role === 'user').map(m => m.text)).toEqual(['改写的第一问'])
    expect(streamUtter).toHaveBeenCalledTimes(1)
  })

  /** regenerate：分叉到前一条用户消息（含），去掉本条回复后用原话重跑。
   *  Regenerate: fork to the user message before it (inclusive), drop this reply,
   *  rerun with the original words. */
  it('regenerate 分叉到原问题并重跑', async () => {
    messages.value = [mkMsg('user', '问题'), mkMsg('assistant', '要重生成的回答'), mkMsg('user', '后续')]
    vi.mocked(api.forkSession).mockResolvedValue({ ok: true, session: { id: 's2' } as any })

    const ok = await regenerate(1)
    expect(ok).toBe(true)
    expect(api.forkSession).toHaveBeenCalledWith('s1', 0)   // 前缀含原问题。Prefix keeps the question.
    expect(messages.value.filter(m => m.role === 'user').map(m => m.text)).toEqual(['问题'])
    expect(streamUtter).toHaveBeenCalledTimes(1)
  })
})
