import { reactive } from 'vue'
import { api, streamUtter } from '../../api'
import { state, messages, tokenUsage, partialText, genId, addMessage, buildHistory, MAX_MESSAGES, pendingQuestion, currentSessionId, assistantMode, textProjection, wakeKeywords } from './store'
import { speakAuto, stopSpeak } from './useTts'
import { matchOption } from './answerMatch'
import { detectWake } from './wakeMatch'
import { applyEvent, finalizeBlocks } from '../../blocks/normalize'
import { speechForBlocks } from '../../blocks/speech'
import type { Block } from '../../blocks/types'
import type { ChatMessage } from './store'
import { CANCEL_RE, enqueue, clearOutbox, flushOutbox } from './useChatOutbox'
import { sendAnswer } from './useChatAnswer'

// ─── 导出门面：outbox / 分叉编辑 / 工具 / 作答拆出为同目录子模块，原导入路径与
//      导出面不变（纯移动）。runTurn/sendText/abortChat/abandonQuestion 留本主体。
// Facade: the outbox / fork-edit / tools / answer clusters live in sibling submodules;
// original import path and export surface unchanged (pure move). runTurn/sendText/
// abortChat/abandonQuestion stay in this hub.
export { outboxCount, clearQueued } from './useChatOutbox'
export { sendAnswer }
export { retryTool, cancelTool } from './useChatTools'
export { forkAt, sendEdited, regenerate } from './useChatHistoryEdit'

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

/** 弃题（待答期间命中唤醒词，文字侧）：清问题卡 + stopTask 解除后端 ask() 阻塞
 *  （T1 毒丸），state 回 **thinking** —— 回合仍在跑（等 done），且新指令必须入队
 *  等收束（直连 utter 撞该会话的 409 busy 检查）。与 wakeOrchestrator 的
 *  abandonPendingQuestion 同语义（DI 边界各持一份，互为参照）。
 *
 *  Abandon (wake word hit while awaiting, text side): clear the card + stopTask to
 *  unblock the backend ask() (the T1 poison pill); state returns to **thinking** — the
 *  turn is still running (awaiting done) and a new instruction must queue for the
 *  wrap-up (a direct utter would hit that session's 409 busy check). Same semantics as
 *  wakeOrchestrator's abandonPendingQuestion (one copy per DI boundary; cross-referenced). */
export function abandonQuestion(): void {
  if (!pendingQuestion.value) return
  pendingQuestion.value = null
  state.value = 'thinking'
  const sid = currentSessionId.value
  if (sid) void api.stopTask?.(sid)?.catch?.(() => { /* 尽力而为。Best effort. */ })
}

/** 回合代际：迟到的旧回合回调不得改动新回合状态（onAbort done 覆盖 thinking 的竞态，
 *  docs/designs/06 批3）。旧回合的一切 handler 先比对代际再动状态。
 *  Turn generation: late callbacks from an old turn must not mutate the new turn's state
 *  (the race where a late onAbort's done overwrites thinking, docs/designs/06 batch 3).
 *  Every handler of an old turn checks the generation before touching state. */
let runGen = 0

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

/** 文字输入（与语音共用 LLM 管线）。分流规则（docs/designs/06 批3；弃题分支见 03 取消限时回答）：
 *  1. 取消词 → 立即中止 + 清队（排队不得吞掉取消）；
 *  2. 有待答问题 → 先判唤醒词（命中 → 弃题开新轮），未命中 → 转作答语义
 *     （选项 trim 精确匹配转结构化 choice），不排队；
 *  3. 回合进行中 → 入 outbox 排队，收束自动连发；
 *  4. 空闲 → 直接起一轮。
 *
 *  Text input (shares the LLM pipeline with voice). Routing (docs/designs/06 batch 3;
 *  the abandon branch: docs/designs/03 unlimited answer window):
 *  1. cancel word → abort now + clear the queue (the queue must never swallow a cancel);
 *  2. a pending question → wake word checked first (a hit abandons and starts a fresh
 *     turn), otherwise answer semantics (option trim-exact match becomes a structured
 *     choice), never queued;
 *  3. turn running → queue in the outbox, flushed when the turn wraps up;
 *  4. idle → start a turn directly.
 *
 *  @param text - 用户输入文本。User input text. */
export function sendText(text: string) {
  let t = text.trim()
  if (!t) return
  if (CANCEL_RE.test(t)) {
    abortChat()
    clearOutbox()
    return
  }
  // 待答问题优先：在输入框回答 = 作答（否则会被排队压到回合结束后，作答就死了）。
  // 先判唤醒词（本地拼音匹配）：命中 → 弃题开新轮（带指令则指令作新文本往下走，
  // state 已回 thinking → 满足入队条件；裸词只弃题），未命中 → 照旧作答。
  // A pending question wins first: typing an answer IS an answer (queuing it until the
  // turn ends would kill the answer flow). The wake word is checked first (local pinyin
  // match): a hit abandons and starts a fresh turn (a command becomes the new text
  // flowing down — state already returned to thinking so it satisfies the enqueue
  // condition; a bare word only abandons), a miss answers as before.
  const pq = pendingQuestion.value
  if (pq) {
    const wake = detectWake(t, wakeKeywords.value)
    if (wake.matched) {
      abandonQuestion()
      if (!wake.command) return   // 裸唤醒：文字侧只弃题（不开指令窗）。Bare wake: abandon only.
      t = wake.command            // 指令当新文本：入队等 done 收束连发。Command as new text: queued for the wrap-up chain.
    } else {
      const hit = matchOption(t, pq.options)
      void sendAnswer(hit ? '' : t, hit?.value, 'typed')
      return
    }
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
