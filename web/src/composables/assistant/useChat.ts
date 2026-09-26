import { reactive } from 'vue'
import { api, streamUtter } from '../../api'
import { formatError } from '../../errors'
import { state, messages, tokenUsage, partialText, genId, addMessage, addBlocks, buildHistory, MAX_MESSAGES, pendingQuestion, currentSessionId, assistantMode, textProjection } from './store'
import { speakAuto } from './useTts'
import { applyEvent, finalizeBlocks, makeBlock } from '../../blocks/normalize'
import { speechForBlocks } from '../../blocks/speech'
import type { Block } from '../../blocks/types'
import type { ChatMessage } from './store'

/** 流式对话中止句柄（取消/停止按钮用）。Abort handle for streaming conversation (for cancel/stop buttons). */
let abortController: AbortController | null = null

/** 中止当前 SSE 流（用户取消 / 页面销毁时调用）。
 *  Abort current SSE stream (called on user cancel / page destruction). */
export function abortChat() {
  abortController?.abort()
  abortController = null
}

/** 消费编排 SSE 流（唯一 agent 路径；工具由后端执行，前端只展示）。
 *  Consume orchestration SSE stream (single agent path; tools executed by backend, frontend only displays).
 *  副作用：更新状态、消息、token 使用量等响应式状态。Side effects: update state, messages, token usage, etc. reactive state. */
export async function runTurn() {
  const last = messages.value[messages.value.length - 1]
  if (!last || last.role !== 'user') return  // 只对用户话语启动一轮。Only start a turn for user utterances.
  const text = last.text
  state.value = 'thinking'
  const history = buildHistory()

  // 中止上一次未结束的流（防并发覆盖）。
  // Abort previous unfinished stream (prevent concurrent overwrite).
  abortController?.abort()
  abortController = new AbortController()

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
      if (s.session_id) currentSessionId.value = s.session_id
      if (s.state === 'understanding') state.value = 'thinking'
    },
    onContent: () => { state.value = 'responding' },
    onReasoning: () => { /* 思考流经 onEvent 进 thinking 块（折叠展示、默认不播）。Reasoning flows into the thinking block via onEvent. */ },
    onToolStart: () => { state.value = 'tool_calling' },
    onToolEnd: () => {},
    onUsage: (u) => {
      // 编排 ReAct 每轮可能多次 completion，按会话累计。
      // Orchestration ReAct may have multiple completions per round, accumulate by session.
      tokenUsage.value.prompt_tokens = (tokenUsage.value.prompt_tokens || 0) + (u.prompt_tokens || 0)
      tokenUsage.value.completion_tokens = (tokenUsage.value.completion_tokens || 0) + (u.completion_tokens || 0)
      tokenUsage.value.total_tokens = (tokenUsage.value.total_tokens || 0) + (u.total_tokens || 0)
    },
    onQuestion: ({ question, session_id, kind, options, qid }) => {
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
    },
    onAbort: () => {
      // 用户主动取消（cancelTool 触发），非错误。
      // User actively cancels (triggered by cancelTool), not an error.
      if (textFlushTimer) { clearTimeout(textFlushTimer); textFlushTimer = null }
      finalizeBlocks(turnBlocks as unknown as Block[])
      partialText.value = ''
      pendingQuestion.value = null
      state.value = 'done'
    },
    onError: (msg) => {
      if (textFlushTimer) { clearTimeout(textFlushTimer); textFlushTimer = null }
      console.error('[Asst] LLM error:', msg)
      addMessage('system', '出错了: ' + msg)
      pendingQuestion.value = null
      speakAuto('出错了：' + msg)
      state.value = 'error'
    },
  }, { messages: history, sessionId: currentSessionId.value || undefined,
       signal: abortController.signal, mode: assistantMode.value })
  // 流结束（含未走 onDone 的路径）强制同步文本投影，保证 text 与块一致。
  // Force-sync the text projection when the stream ends (including paths without
  // onDone), keeping text consistent with the blocks.
  flushSync()
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
    addBlocks('user', [makeBlock('answer', { qid, text: label, choice: choice ?? null, source })])
    pendingQuestion.value = null
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

/** 文字输入（与语音共用 LLM 管线）。
 *  Text input (shares LLM pipeline with voice).
 *  @param text - 用户输入文本。User input text. */
export function sendText(text: string) {
  const t = text.trim()
  if (!t) return
  addMessage('user', t)
  void runTurn()
}
