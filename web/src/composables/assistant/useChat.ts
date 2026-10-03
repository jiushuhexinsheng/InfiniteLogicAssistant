import { reactive, ref } from 'vue'
import { api, streamUtter } from '../../api'
import { formatError } from '../../errors'
import { state, messages, tokenUsage, partialText, genId, addMessage, addBlocks, buildHistory, MAX_MESSAGES, pendingQuestion, currentSessionId, assistantMode, textProjection } from './store'
import { speakAuto, stopSpeak } from './useTts'
import { matchOption } from './answerMatch'
import { applyEvent, attachAnswer, finalizeBlocks, makeBlock } from '../../blocks/normalize'
import { speechForBlocks } from '../../blocks/speech'
import type { Block } from '../../blocks/types'
import type { ChatMessage } from './store'

/** 流式对话中止句柄（取消/停止按钮用）。Abort handle for streaming conversation (for cancel/stop buttons). */
let abortController: AbortController | null = null

/** 中止当前 SSE 流（用户取消 / 页面销毁时调用）。
 *  Abort current SSE stream (called on user cancel / page destruction).
 *
 *  服务端宽限机制（docs/designs/06）下「断线不再自动停任务」——显式中止必须补一枪
 *  stop 端点，否则取消按钮只断了本地流、任务还在服务器跑。
 *  Under the server grace mechanism (docs/designs/06) a disconnect no longer stops
 *  the task on its own — an explicit abort must also hit the stop endpoint, or the
 *  cancel button only severs the local stream while the task keeps running. */
export function abortChat() {
  abortController?.abort()
  abortController = null
  const sid = currentSessionId.value
  if (sid) void api.stopTask?.(sid)?.catch?.(() => { /* 尽力而为。Best effort. */ })
}

/** 回合代际：迟到的旧回合回调不得改动新回合状态（onAbort done 覆盖 thinking 的竞态，
 *  docs/designs/06 批3）。旧回合的一切 handler 先比对代际再动状态。
 *  Turn generation: late callbacks from an old turn must not mutate the new turn's state
 *  (the race where a late onAbort's done overwrites thinking, docs/designs/06 batch 3).
 *  Every handler of an old turn checks the generation before touching state. */
let runGen = 0

/** 待发消息队列：回合进行中用户再发 → 入队，回合收束自动连发（Open WebUI 式消息队列）。
 *  Outbox: sending while a turn runs queues the message; turn end flushes it
 *  (the Open WebUI-style message queue). */
const outbox: string[] = []

/** 队列长度（响应式，供输入框「排队中」徽标）。Queue length (reactive, for the input's
 *  "queued" badge). */
export const outboxCount = ref(0)

/** 取消词：立即中止并清队（排队不得吞掉取消）。Cancellation words: abort at once and
 *  clear the queue (the queue must never swallow a cancel). */
const CANCEL_RE = /^(停止|取消|暂停|算了|别跑了|stop|cancel)$/i

function enqueue(t: string) {
  outbox.push(t)
  outboxCount.value = outbox.length
}

function clearOutbox() {
  outbox.length = 0
  outboxCount.value = 0
}

/** 回合收束后弹出下一条排队消息（链条式：每回合收束弹一条）。
 *  Pop the next queued message after a turn wraps up (chained: one per turn end). */
function flushOutbox() {
  const t = outbox.shift()
  outboxCount.value = outbox.length
  if (!t) return
  addMessage('user', t)
  void runTurn()
}

/** 消费编排 SSE 流（唯一 agent 路径；工具由后端执行，前端只展示）。
 *  Consume orchestration SSE stream (single agent path; tools executed by backend, frontend only displays).
 *  副作用：更新状态、消息、token 使用量等响应式状态。Side effects: update state, messages, token usage, etc. reactive state. */
export async function runTurn() {
  const last = messages.value[messages.value.length - 1]
  if (!last || last.role !== 'user') return  // 只对用户话语启动一轮。Only start a turn for user utterances.
  const gen = ++runGen   // 认领代际：此后所有回调先过 alive() 再动状态。Claim the generation.
  const alive = () => gen === runGen
  const text = last.text
  state.value = 'thinking'
  const history = buildHistory()

  // 中止上一次未结束的流（防并发覆盖）。
  // Abort previous unfinished stream (prevent concurrent overwrite).
  abortController?.abort()
  abortController = new AbortController()
  // 新回合立即掐断旧播报（打断白名单：任何播报可被新回合打断，docs/designs/02 §3.1）。
  // 不打断会出现「旧回复继续念、与新回合叠音」。
  // Silence the previous playback immediately (interrupt whitelist: any playback is
  // interruptible by a new round, docs/designs/02 §3.1); without it the old reply
  // keeps reading over the new round.
  stopSpeak('new_turn')

  let currentMsg: ChatMessage | null = null
  // 块列表（事实源）：全部 SSE 事件经 applyEvent 归一进这里。
  // Block list (source of truth): all SSE events are normalized in via applyEvent.
  const turnBlocks = reactive<Block[]>([])

  /** 确保当前消息存在，不存在则创建。Ensure current message exists, create if not. */
  const ensureMsg = () => {
    if (!currentMsg) {
      const msg = { id: genId(), role: 'assistant' as const, text: '', blocks: turnBlocks as unknown as Block[], timestamp: Date.now() }
      messages.value.push(msg)
      if (messages.value.length > MAX_MESSAGES) messages.value.shift()
      // 取回数组内的响应式 proxy 再写入，否则直接改 raw 对象不会触发任何重渲染。
      // Retrieve the reactive proxy from the array before writing, otherwise direct raw object changes won't trigger re-renders.
      currentMsg = messages.value[messages.value.length - 1]
    }
    return currentMsg
  }

  // 流式文本投影节流：块变更后重算 text 投影（50ms 合并，结束时 flush）。
  // Streaming projection throttle: recompute the text projection after block
  // changes (batched at 50ms, flushed at the end).
  let textFlushTimer: ReturnType<typeof setTimeout> | null = null
  const syncProjection = () => {
    const m = ensureMsg()
    m.text = textProjection(turnBlocks as unknown as Block[])
  }
  const scheduleSync = () => {
    if (textFlushTimer) return
    textFlushTimer = setTimeout(() => {
      textFlushTimer = null
      syncProjection()
    }, 50)
  }
  const flushSync = () => {
    if (textFlushTimer) { clearTimeout(textFlushTimer); textFlushTimer = null }
    syncProjection()
  }

  await streamUtter(text, {
    onEvent: (ev) => {
      if (!alive()) return  // 旧回合迟到事件不得改旧块流（防 streaming 卡死）。Late events of an old turn must not touch its blocks.
      // 块 reducer：事件 → 块流（模块化数据层的唯一入口）。
      // 消息随首个事件即刻创建（块是响应式的）；文本投影计算才节流。
      // Block reducer: events → block stream (the single entry of the modular data
      // layer). The message is created on the first event (blocks are reactive);
      // only the text projection is throttled.
      applyEvent(ev, turnBlocks as unknown as Block[])
      ensureMsg()
      scheduleSync()
    },
    onTaskState: (s) => {
      if (!alive()) return
      if (s.session_id) currentSessionId.value = s.session_id
      if (s.state === 'understanding') state.value = 'thinking'
    },
    onContent: () => { if (alive()) state.value = 'responding' },
    onReasoning: () => { /* 思考流经 onEvent 进 thinking 块（折叠展示、默认不播）。Reasoning flows into the thinking block via onEvent. */ },
    onToolStart: () => { if (alive()) state.value = 'tool_calling' },
    onToolEnd: () => {},
    onUsage: (u) => {
      if (!alive()) return
      // 编排 ReAct 每轮可能多次 completion，按会话累计。
      // Orchestration ReAct may have multiple completions per round, accumulate by session.
      tokenUsage.value.prompt_tokens = (tokenUsage.value.prompt_tokens || 0) + (u.prompt_tokens || 0)
      tokenUsage.value.completion_tokens = (tokenUsage.value.completion_tokens || 0) + (u.completion_tokens || 0)
      tokenUsage.value.total_tokens = (tokenUsage.value.total_tokens || 0) + (u.total_tokens || 0)
    },
    onQuestion: ({ question, session_id, kind, options, qid }) => {
      if (!alive()) return
      currentSessionId.value = session_id
      // kind 与 options 决定前端渲染按钮还是输入框；缺省按文本处理。
      // kind and options decide buttons vs. an input; default to text.
      pendingQuestion.value = {
        text: question,
        kind: kind === 'choice' || kind === 'composite' ? kind : 'text',
        options: options ?? [],
        qid,
      }
      speakAuto(question)  // 澄清/确认问题语音播报。Clarification/confirmation questions are spoken.
      state.value = 'thinking'
    },
    onDone: (sessionId) => {
      if (!alive()) return
      if (sessionId) currentSessionId.value = sessionId
      pendingQuestion.value = null
      finalizeBlocks(turnBlocks as unknown as Block[])
      flushSync()
      partialText.value = ''
      // 语音播报统一出口：回合汇总卡 tts_text → 块级策略拼接 → 兜底
      // Unified speech exit: summary tts_text → block-policy join → fallback.
      const speech = speechForBlocks(turnBlocks as unknown as Block[])
      if (speech.trim()) speakAuto(speech)
      else if (turnBlocks.some(b => b.type === 'tool')) speakAuto('已完成')
      state.value = 'done'
      flushOutbox()   // 收束即连发下一条排队消息。Chain the next queued message.
    },
    onAbort: () => {
      if (!alive()) return
      // 用户主动取消（cancelTool 触发），非错误。
      // User actively cancels (triggered by cancelTool), not an error.
      if (textFlushTimer) { clearTimeout(textFlushTimer); textFlushTimer = null }
      finalizeBlocks(turnBlocks as unknown as Block[])
      partialText.value = ''
      pendingQuestion.value = null
      state.value = 'done'
      flushOutbox()
    },
    onError: (msg) => {
      if (!alive()) return
      if (textFlushTimer) { clearTimeout(textFlushTimer); textFlushTimer = null }
      console.error('[Asst] LLM error:', msg)
      addMessage('system', '出错了: ' + msg)
      pendingQuestion.value = null
      speakAuto('出错了：' + msg)
      state.value = 'error'
      flushOutbox()
    },
  }, { messages: history, sessionId: currentSessionId.value || undefined,
       signal: abortController.signal, mode: assistantMode.value })
  // 流结束（含未走 onDone 的路径）强制同步文本投影，保证 text 与块一致。
  // Force-sync the text projection when the stream ends (including paths without
  // onDone), keeping text consistent with the blocks.
  if (alive()) flushSync()
}

/** 回答澄清/确认问题（解除后端 ask() 阻塞）。
 *  Answer clarification/confirmation question (unblock backend ask() call).
 *  @param text - 用户回答文本（选择类提问为空）。User answer text (empty for choice questions).
 *  @param choice - 结构化选择的取值（由选项按钮回传）。The structured selection returned by the option buttons.
 *  @param source - 作答通道（typed/voice/button），语音作答可审计。Answer channel (voice answers auditable). */
export async function sendAnswer(text: string, choice?: string, source: string = 'typed') {
  const t = text.trim()
  // 结构化选择可以不带文本；两者皆空则不投递（避免空回答解除后端阻塞）。
  // A structured choice may carry no text; when both are empty, don't deliver
  // (avoiding an empty answer that would unblock the backend).
  if (!t && !choice) return
  if (!currentSessionId.value) return
  // 记录用文本：选择类取被选选项的 label（人类可读），文本类取输入文本。
  // Record text: a choice takes the selected option's label (human-readable), a text answer its own text.
  const qid = pendingQuestion.value?.qid
  const label = choice
    ? (pendingQuestion.value?.options.find((o) => o.value === choice)?.label || choice)
    : t
  try {
    await api.answer(currentSessionId.value, t, choice, { qid, source })
    // 仅在投递成功后写记录，避免记录与后端状态不一致。
    // Record only after a successful delivery, so the record cannot disagree with the backend.
    // 配对问题在某条消息里 → 答案贴进该卡片（问题块紧后，修「问题和回答分离」）；
    // 找不到（无 qid / 流已死）才落独立用户气泡兜底。
    // Paired question lives in a message → attach the answer into that card right
    // after the question block (fixes Q/A split apart); fall back to a standalone
    // user bubble only when no holder exists (no qid / dead stream).
    const holder = qid
      ? messages.value.find(m => m.blocks?.some(b => b.type === 'question' && b.payload.qid === qid))
      : undefined
    if (qid && holder?.blocks) {
      attachAnswer(holder.blocks, { qid, text: label, choice: choice ?? null, source })
    } else {
      addBlocks('user', [makeBlock('answer', { qid, text: label, choice: choice ?? null, source })])
    }
    pendingQuestion.value = null
    // 已作答：问题还在被朗读的话就停掉（用户已经用行动回答了，不必念完）。
    // Answered: stop the question reading if it is still going (the user already
    // answered by action; it need not finish reading).
    stopSpeak('new_turn')
  } catch (e) {
    addMessage('system', '回答投递失败：' + formatError(e))
  }
}

/** 在消息块里找工具块（按 call_id / 块 id）。Find a tool block by call_id / block id. */
function findToolBlock(id: string): Block | undefined {
  for (const msg of messages.value) {
    for (const b of msg.blocks || []) {
      if (b.type === 'tool' && (b.payload.call_id === id || b.id === id)) return b
    }
  }
  return undefined
}

/** 工具重试：失败的工具走后端真实重跑，再用修正结果续一轮对话。
 *  Tool retry: failed tool reruns on backend, then continues conversation with corrected result.
 *  @param id - 工具调用 ID。Tool call ID. */
export async function retryTool(id: string) {
  const blk = findToolBlock(id)
  if (!blk) return

  blk.payload.status = 'running'
  blk.payload.output = ''
  blk.payload.output_preview = ''
  state.value = 'tool_calling'

  const startTs = Date.now()
  try {
    // 高风险工具（后端返回 needs_confirm）先弹确认，确认后再带 confirm 重调。
    // High-risk tools (backend returns needs_confirm) prompt confirmation first, then re-invoke with confirm flag.
    let r = await api.callTool(blk.payload.name, blk.payload.args || {})
    if (r.needs_confirm) {
      const ok = window.confirm(`确认执行高风险工具「${blk.payload.name}」？\n参数：${JSON.stringify(blk.payload.args || {})}`)
      r = ok
        ? await api.callTool(blk.payload.name, blk.payload.args || {}, true)
        : { ok: false, status: 'error', error: '用户取消确认' }
    }
    if (r.ok) {
      blk.payload.status = r.status === 'ok' ? 'ok' : 'error'
      blk.payload.output = r.output || ''
      blk.payload.output_preview = (r.output || '').slice(0, 500)
    } else {
      blk.payload.status = 'error'
      blk.payload.output = r.error || '执行失败'
      blk.payload.output_preview = blk.payload.output
    }
  } catch (e) {
    blk.payload.status = 'error'
    // 兜底用领域化的「执行失败」，比通用的「未知错误」更能说明发生了什么
    // Fall back to the domain-specific "执行失败", which conveys more than a generic message.
    blk.payload.output = formatError(e, '执行失败')
    blk.payload.output_preview = blk.payload.output
  }
  blk.payload.duration_ms = Date.now() - startTs
  // 不再自动续轮：编排管线按新话语驱动，用户可发「继续」等新话语，历史随 messages 种子带入。
  // No longer auto-continue: orchestration pipeline driven by new utterances, users can send "continue" etc., history seeded with messages.
}

/** 工具/回复取消：中止后端 SSE 流，本地将运行中的步骤标记为已取消。
 *  Tool/reply cancel: abort backend SSE stream, locally mark running steps as cancelled.
 *  @param id - 工具调用 ID。Tool call ID. */
export function cancelTool(id: string) {
  abortChat()
  const blk = findToolBlock(id)
  if (blk && (blk.payload.status === 'running' || !blk.payload.status)) {
    blk.payload.status = 'cancelled'
    blk.payload.output = '已取消'
    blk.payload.output_preview = '已取消'
  }
}

/** 文字输入（与语音共用 LLM 管线）。分流规则（docs/designs/06 批3）：
 *  1. 取消词 → 立即中止 + 清队（排队不得吞掉取消）；
 *  2. 有待答问题 → 转作答语义（选项 trim 精确匹配转结构化 choice），不排队；
 *  3. 回合进行中 → 入 outbox 排队，收束自动连发；
 *  4. 空闲 → 直接起一轮。
 *
 *  Text input (shares the LLM pipeline with voice). Routing (docs/designs/06 batch 3):
 *  1. cancel word → abort now + clear the queue (the queue must never swallow a cancel);
 *  2. a pending question → answer semantics (option trim-exact match becomes a
 *     structured choice), never queued;
 *  3. turn running → queue in the outbox, flushed when the turn wraps up;
 *  4. idle → start a turn directly.
 *
 *  @param text - 用户输入文本。User input text. */
export function sendText(text: string) {
  const t = text.trim()
  if (!t) return
  if (CANCEL_RE.test(t)) {
    abortChat()
    clearOutbox()
    return
  }
  // 待答问题优先：在输入框回答 = 作答（否则会被排队压到回合结束后，作答就死了）。
  // A pending question wins first: typing an answer IS an answer (queuing it until the
  // turn ends would kill the answer flow).
  const pq = pendingQuestion.value
  if (pq) {
    const hit = matchOption(t, pq.options)
    void sendAnswer(hit ? '' : t, hit?.value, 'typed')
    return
  }
  // 回合**真正进行中**（LLM 流在跑）才排队；其余状态一律直接发送。
  // ⚠️ 回归靶子：唤醒指令与续聊窗口接话分别落在 listening / followup / recording /
  // transcribing 这些语音链状态 —— 曾把它们误判为「回合中」入队，而这些状态下没有任何
  // 在跑的回合会触发 flushOutbox，消息就永远卡在「排队」（实测：唤醒后说「你好」只显示排队）。
  // Queue only while a turn is **truly running** (LLM stream in flight); every other
  // state sends immediately. Regression target: wake commands and follow-up replies
  // ride the voice-chain states listening / followup / recording / transcribing —
  // misclassifying them as "a turn is running" queued the message with no live turn
  // to ever flush it, so it sat at "queued" forever (observed: after wake, saying
  // "你好" only showed the queue badge).
  const TURN_RUNNING = ['thinking', 'tool_calling', 'responding']
  if (TURN_RUNNING.includes(state.value)) {
    enqueue(t)
    return
  }
  addMessage('user', t)
  void runTurn()
}

/** 清空排队消息（输入框徽标点击）。Clear queued messages (input badge click). */
export function clearQueued() {
  clearOutbox()
}

// ── 会话分叉 / 编辑重发 / 重新生成（docs/designs/07）──
// 约束：整段覆盖式存储下，改写历史必须先分叉（源会话在服务端只读不动）；
// 回合进行中一律禁用（与排队机制的「显式动作」边界一致）。

/** 是否处于可做分叉/编辑动作的空闲态。Whether we are idle enough for fork/edit actions. */
function idleForEdit(): boolean {
  return state.value === 'done' || state.value === 'error' || state.value === 'idle'
}

/** 从 index 处（含该条）分叉：服务端复制前缀为新会话，本地截断并切到新 id。
 *  前缀内容本地与服务端一致，省一次历史拉取。失败返回 false。
 *
 *  Fork at index (inclusive): the server copies the prefix into a new conversation;
 *  locally truncate and switch to the new id. The prefix is identical on both sides,
 *  so no history refetch is needed. Returns false on failure.
 *
 *  @param index - 分叉边界消息下标（含）。Fork boundary message index (inclusive). */
export async function forkAt(index: number): Promise<boolean> {
  if (!idleForEdit()) return false
  const sid = currentSessionId.value
  if (!sid || index < 0 || index >= messages.value.length) return false
  try {
    const r = await api.forkSession(sid, index)
    if (!r.ok) return false
    const prefix = messages.value.slice(0, index + 1)
    currentSessionId.value = r.session.id
    messages.value = prefix
    pendingQuestion.value = null
    tokenUsage.value = {}
    return true
  } catch (e) {
    addMessage('system', '分叉失败：' + formatError(e))
    return false
  }
}

/** 编辑 index 处的用户消息并重发：非末条先分叉（保原路径），改写后起新一轮。
 *
 *  Edit the user message at index and resend: non-tail messages fork first (the
 *  original path is kept); rewrite then start a new turn.
 *
 *  @param index - 被编辑消息下标。Index of the edited message.
 *  @param newText - 新文本。The new text.
 *  @returns 是否成功。Whether it succeeded. */
export async function sendEdited(index: number, newText: string): Promise<boolean> {
  const t = newText.trim()
  if (!t || !idleForEdit()) return false
  const target = messages.value[index]
  if (!target || target.role !== 'user') return false
  if (index < messages.value.length - 1) {
    const ok = await forkAt(index)     // 保原路径（编辑必须先分叉）。Keep the original path.
    if (!ok) return false
  } else {
    messages.value.splice(index + 1)   // 末条编辑：防御性截尾。Tail edit: defensive trim.
  }
  const m = messages.value[index]
  m.text = t
  m.blocks = [makeBlock('text', { md: t, variant: 'bubble' })]
  void runTurn()
  return true
}

/** 重新生成 index 处的助手回复：分叉到其前一条用户消息（含），用原话重跑一轮。
 *
 *  Regenerate the assistant reply at index: fork to the user message before it
 *  (inclusive) and rerun that turn with the original words.
 *
 *  @param index - 被重新生成的助手消息下标。Index of the assistant message.
 *  @returns 是否成功。Whether it succeeded. */
export async function regenerate(index: number): Promise<boolean> {
  if (!idleForEdit()) return false
  const m = messages.value[index]
  if (!m || m.role !== 'assistant') return false
  let u = -1
  for (let i = index - 1; i >= 0; i--) {
    if (messages.value[i].role === 'user') { u = i; break }
  }
  if (u < 0) return false
  const ok = await forkAt(u)           // 前缀含原问题、去掉本条回复。Prefix keeps the question, drops this reply.
  if (!ok) return false
  void runTurn()                        // 末条是用户消息 → 直接重跑。Last message is the user's → rerun.
  return true
}
