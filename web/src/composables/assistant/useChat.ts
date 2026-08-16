import { reactive } from 'vue'
import { api, streamUtter } from '../../api'
import { state, messages, tokenUsage, partialText, genId, addMessage, buildHistory, MAX_MESSAGES, pendingQuestion, currentSessionId } from './store'
import { speakText } from './useTts'
import type { ChatMessage, ToolCall } from './store'

// ── 流式对话中止句柄（取消/停止按钮用）──
let abortController: AbortController | null = null

/** 中止当前 SSE 流（用户取消 / 页面销毁时调用） */
export function abortChat() {
  abortController?.abort()
  abortController = null
}

// 消费编排 SSE 流（唯一 agent 路径；工具由后端执行，前端只展示）
export async function runTurn() {
  const last = messages.value[messages.value.length - 1]
  if (!last || last.role !== 'user') return  // 只对用户话语启动一轮
  const text = last.text
  state.value = 'thinking'
  const history = buildHistory()

  // 中止上一次未结束的流（防并发覆盖）
  abortController?.abort()
  abortController = new AbortController()

  let acc = ''
  let currentMsg: ChatMessage | null = null
  // 用 reactive 数组承载工具调用，onToolStart/onToolEnd 的增删改才能触发 UI 更新
  const toolAcc = reactive<ToolCall[]>([])
  const toolStartMap = new Map<string, number>()

  const ensureMsg = () => {
    if (!currentMsg) {
      const msg = { id: genId(), role: 'assistant' as const, text: '', toolCalls: toolAcc, timestamp: Date.now() }
      messages.value.push(msg)
      if (messages.value.length > MAX_MESSAGES) messages.value.shift()
      // 取回数组内的响应式 proxy 再写入，否则直接改 raw 对象不会触发任何重渲染
      currentMsg = messages.value[messages.value.length - 1]
    }
    return currentMsg
  }

  // 流式文本写入节流：content_delta 高频到达，若每次直接 message.text=acc，
  // 会整条消息跑一遍 markdown 正则。合并到 ~50ms 一次；结束时强制 flush。
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
      // notify / done 的状态提示由消息文本呈现，无需额外处理
    },
    onContent: (t) => {
      state.value = 'responding'
      acc += t
      partialText.value = acc
      scheduleText()
    },
    onReasoning: () => { /* 前端不展示思考过程，忽略 */ },
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
      // 编排 ReAct 每轮可能多次 completion，按会话累计
      tokenUsage.value.prompt_tokens = (tokenUsage.value.prompt_tokens || 0) + (u.prompt_tokens || 0)
      tokenUsage.value.completion_tokens = (tokenUsage.value.completion_tokens || 0) + (u.completion_tokens || 0)
      tokenUsage.value.total_tokens = (tokenUsage.value.total_tokens || 0) + (u.total_tokens || 0)
    },
    onQuestion: ({ question, session_id }) => {
      currentSessionId.value = session_id
      pendingQuestion.value = question
      state.value = 'thinking'
    },
    onDone: (sessionId) => {
      if (sessionId) currentSessionId.value = sessionId
      pendingQuestion.value = ''
      flushText()
      partialText.value = ''
      if (acc.trim()) speakText(acc)
      else if (toolAcc.length) speakText('已完成')
      state.value = 'done'
    },
    onAbort: () => {
      // 用户主动取消（cancelTool 触发），非错误
      if (textFlushTimer) { clearTimeout(textFlushTimer); textFlushTimer = null }
      partialText.value = ''
      pendingQuestion.value = ''
      state.value = 'done'
    },
    onError: (msg) => {
      if (textFlushTimer) { clearTimeout(textFlushTimer); textFlushTimer = null }
      console.error('[Asst] LLM error:', msg)
      addMessage('system', '出错了: ' + msg)
      pendingQuestion.value = ''
      state.value = 'error'
    },
  }, { messages: history, signal: abortController.signal })
}

// ── 回答澄清/确认问题（解除后端 ask() 阻塞）──
export async function sendAnswer(text: string) {
  const t = text.trim()
  if (!t || !currentSessionId.value) return
  try {
    await api.answer(currentSessionId.value, t)
    pendingQuestion.value = ''
  } catch (e: any) {
    addMessage('system', '回答投递失败: ' + (e?.message || ''))
  }
}

// ── 工具重试：失败的工具走后端真实重跑，再用修正结果续一轮对话 ──
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
    const r = await api.callTool(tc.name, tc.args || {})
    if (r.ok) {
      tc.status = r.status === 'ok' ? 'done' : 'failed'
      tc.result = r.output || ''
    } else {
      tc.status = 'failed'
      tc.result = r.error || '执行失败'
    }
  } catch (e: any) {
    tc.status = 'failed'
    tc.result = e?.message || '执行失败'
  }
  tc.durationMs = Date.now() - startTs
  // 不再自动续轮：编排管线按新话语驱动，用户可发「继续」等新话语，历史随 messages 种子带入
}

// ── 工具/回复取消：中止后端 SSE 流，本地将运行中的步骤标记为已取消 ──
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

// ── 文字输入（与语音共用 LLM 管线）──
export function sendText(text: string) {
  const t = text.trim()
  if (!t) return
  addMessage('user', t)
  void runTurn()
}
