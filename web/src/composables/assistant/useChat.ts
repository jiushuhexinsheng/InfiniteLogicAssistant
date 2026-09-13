import { reactive } from 'vue'
import { api, streamUtter } from '../../api'
import { formatError } from '../../errors'
import { state, messages, tokenUsage, partialText, genId, addMessage, buildHistory, MAX_MESSAGES, pendingQuestion, currentSessionId } from './store'
import { speakAuto } from './useTts'
import type { ChatMessage, ToolCall } from './store'

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

  let acc = ''
  let lastSummary = ''  // 多智能体等 task_state(done) 携带的最终摘要（语音兜底）。Final summary from task_state(done) for voice fallback.
  let currentMsg: ChatMessage | null = null
  // 用 reactive 数组承载工具调用，onToolStart/onToolEnd 的增删改才能触发 UI 更新。
  // Use reactive array for tool calls so onToolStart/onToolEnd changes trigger UI updates.
  const toolAcc = reactive<ToolCall[]>([])
  const toolStartMap = new Map<string, number>()

  /** 确保当前消息存在，不存在则创建。Ensure current message exists, create if not. */
  const ensureMsg = () => {
    if (!currentMsg) {
      const msg = { id: genId(), role: 'assistant' as const, text: '', toolCalls: toolAcc, timestamp: Date.now() }
      messages.value.push(msg)
      if (messages.value.length > MAX_MESSAGES) messages.value.shift()
      // 取回数组内的响应式 proxy 再写入，否则直接改 raw 对象不会触发任何重渲染。
      // Retrieve the reactive proxy from the array before writing, otherwise direct raw object changes won't trigger re-renders.
      currentMsg = messages.value[messages.value.length - 1]
    }
    return currentMsg
  }

  // 流式文本写入节流：content_delta 高频到达，若每次直接 message.text=acc，
  // 会整条消息跑一遍 markdown 正则。合并到 ~50ms 一次；结束时强制 flush。
  // Streaming text write throttle: content_delta arrives high-frequency, direct message.text=acc
  // would run markdown regex on entire message. Batch to ~50ms intervals; force flush on end.
  let textFlushTimer: ReturnType<typeof setTimeout> | null = null
  const scheduleText = () => {
    if (textFlushTimer) return
    textFlushTimer = setTimeout(() => {
      textFlushTimer = null
      ensureMsg().text = acc
    }, 50)
  }
  const flushText = () => {
    if (textFlushTimer) { clearTimeout(textFlushTimer); textFlushTimer = null }
    if (acc) ensureMsg().text = acc
  }

  await streamUtter(text, {
    onTaskState: (s) => {
      if (s.session_id) currentSessionId.value = s.session_id
      if (s.state === 'understanding') state.value = 'thinking'
      if (s.state === 'done' && s.summary) lastSummary = s.summary
      // notify 状态提示由消息文本呈现，无需额外处理。
      // notify status hints are presented by message text, no additional handling needed.
    },
    onContent: (t) => {
      state.value = 'responding'
      acc += t
      partialText.value = acc
      scheduleText()
    },
    onReasoning: () => { /* 前端不展示思考过程，忽略。Frontend doesn't display reasoning process, ignore. */ },
    onToolStart: (name, args) => {
      state.value = 'tool_calling'
      const id = genId()
      toolStartMap.set(id, Date.now())
      toolAcc.push({ id, name, args, status: 'running' })
      ensureMsg()
    },
    onToolEnd: (name, status, output) => {
      const tc = toolAcc.find(t => t.name === name && t.status === 'running')
      if (tc) {
        tc.status = status === 'ok' ? 'done' : 'failed'
        tc.result = output
        const st = toolStartMap.get(tc.id)
        if (st != null) tc.durationMs = Date.now() - st
        toolStartMap.delete(tc.id)
      }
    },
    onUsage: (u) => {
      // 编排 ReAct 每轮可能多次 completion，按会话累计。
      // Orchestration ReAct may have multiple completions per round, accumulate by session.
      tokenUsage.value.prompt_tokens = (tokenUsage.value.prompt_tokens || 0) + (u.prompt_tokens || 0)
      tokenUsage.value.completion_tokens = (tokenUsage.value.completion_tokens || 0) + (u.completion_tokens || 0)
      tokenUsage.value.total_tokens = (tokenUsage.value.total_tokens || 0) + (u.total_tokens || 0)
    },
    onQuestion: ({ question, session_id, kind, options }) => {
      currentSessionId.value = session_id
      // kind 与 options 决定前端渲染按钮还是输入框；缺省按文本处理（向后兼容旧后端）。
      // kind and options decide buttons vs. an input; default to text for an older backend.
      pendingQuestion.value = {
        text: question,
        kind: kind === 'choice' || kind === 'composite' ? kind : 'text',
        options: options ?? [],
      }
      speakAuto(question)  // 澄清/确认问题也语音播报。Clarification/confirmation questions also voice broadcast.
      state.value = 'thinking'
    },
    onDone: (sessionId) => {
      if (sessionId) currentSessionId.value = sessionId
      pendingQuestion.value = null
      flushText()
      partialText.value = ''
      if (acc.trim()) speakAuto(acc)
      else if (lastSummary) speakAuto(lastSummary)  // 多智能体摘要兜底。Multi-agent summary fallback.
      else if (toolAcc.length) speakAuto('已完成')
      state.value = 'done'
    },
    onAbort: () => {
      // 用户主动取消（cancelTool 触发），非错误。
      // User actively cancels (triggered by cancelTool), not an error.
      if (textFlushTimer) { clearTimeout(textFlushTimer); textFlushTimer = null }
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
  }, { messages: history, sessionId: currentSessionId.value || undefined, signal: abortController.signal })
}

/** 回答澄清/确认问题（解除后端 ask() 阻塞）。
 *  Answer clarification/confirmation question (unblock backend ask() call).
 *  @param text - 用户回答文本（确认类提问为空）。User answer text (empty for confirmation questions).
 *  @param choice - 结构化确认选择（"yes"/"no"），由确认按钮回传。Structured confirmation choice ("yes"/"no"), returned by the confirm buttons. */
export async function sendAnswer(text: string, choice?: string) {
  const t = text.trim()
  // 结构化确认可以不带文本；两者皆空则不投递（避免空回答解除后端阻塞）。
  // A structured confirmation may carry no text; when both are empty, don't deliver
  // (avoiding an empty answer that would unblock the backend).
  if (!t && !choice) return
  if (!currentSessionId.value) return
  try {
    await api.answer(currentSessionId.value, t, choice)
    pendingQuestion.value = null
  } catch (e) {
    addMessage('system', '回答投递失败：' + formatError(e))
  }
}

/** 工具重试：失败的工具走后端真实重跑，再用修正结果续一轮对话。
 *  Tool retry: failed tool reruns on backend, then continues conversation with corrected result.
 *  @param id - 工具调用 ID。Tool call ID. */
export async function retryTool(id: string) {
  const m = messages.value.find(msg => msg.toolCalls?.some(tc => tc.id === id))
  const tc = m?.toolCalls?.find(t => t.id === id)
  if (!tc) return

  tc.status = 'running'
  tc.result = ''
  tc.durationMs = undefined
  state.value = 'tool_calling'

  const startTs = Date.now()
  try {
    // 高风险工具（后端返回 needs_confirm）先弹确认，确认后再带 confirm 重调。
    // High-risk tools (backend returns needs_confirm) prompt confirmation first, then re-invoke with confirm flag.
    let r = await api.callTool(tc.name, tc.args || {})
    if (r.needs_confirm) {
      const ok = window.confirm(`确认执行高风险工具「${tc.name}」？\n参数：${JSON.stringify(tc.args || {})}`)
      r = ok
        ? await api.callTool(tc.name, tc.args || {}, true)
        : { ok: false, status: 'error', error: '用户取消确认' }
    }
    if (r.ok) {
      tc.status = r.status === 'ok' ? 'done' : 'failed'
      tc.result = r.output || ''
    } else {
      tc.status = 'failed'
      tc.result = r.error || '执行失败'
    }
  } catch (e) {
    tc.status = 'failed'
    // 兜底用领域化的「执行失败」，比通用的「未知错误」更能说明发生了什么
    // Fall back to the domain-specific "执行失败", which conveys more than a generic message.
    tc.result = formatError(e, '执行失败')
  }
  tc.durationMs = Date.now() - startTs
  // 不再自动续轮：编排管线按新话语驱动，用户可发「继续」等新话语，历史随 messages 种子带入。
  // No longer auto-continue: orchestration pipeline driven by new utterances, users can send "continue" etc., history seeded with messages.
}

/** 工具/回复取消：中止后端 SSE 流，本地将运行中的步骤标记为已取消。
 *  Tool/reply cancel: abort backend SSE stream, locally mark running steps as cancelled.
 *  @param id - 工具调用 ID。Tool call ID. */
export function cancelTool(id: string) {
  abortChat()
  for (const msg of messages.value) {
    msg.toolCalls?.forEach(tc => {
      if (tc.id === id && (tc.status === 'running' || tc.status === 'pending')) {
        tc.status = 'failed'
        tc.result = '已取消'
      }
    })
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
