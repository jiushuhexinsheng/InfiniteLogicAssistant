import type { ApiResponse, ConfigResponse, PingResponse, TextResponse, ToolCallResponse, TokenUsage, ToolsResponse, TaskState } from './types'
import { blobToWavBase64 } from './audio'

// ─── HTTP 封装 ───

const BASE = '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, options)
  if (!res.ok) {
    // 尝试解析 JSON 错误体，失败则用 HTTP 状态码
    let message = `HTTP ${res.status}`
    try {
      const err = await res.json()
      if (err?.error) message = err.error
    } catch { /* not JSON */ }
    throw new Error(message)
  }
  const data = await res.json()
  return data as T
}

async function get<T>(path: string): Promise<T> {
  return request<T>(path)
}

async function post<T>(path: string, data?: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: data ? JSON.stringify(data) : undefined,
  })
}

async function del<T>(path: string): Promise<T> {
  return request<T>(path, { method: 'DELETE' })
}

// ─── API 端点 ───

export const api = {
  ping: () => get<PingResponse>('/ping'),
  getConfig: () => get<ConfigResponse>('/config'),

  // 语音
  transcribe: async (blob: Blob): Promise<TextResponse> => {
    const base64Wav = await blobToWavBase64(blob)
    return post<TextResponse>('/voice/transcribe', { audio_base64: base64Wav })
  },

  // 单工具执行（前端"重试失败工具"走后端真实重跑）
  callTool: async (name: string, args: Record<string, any>): Promise<ToolCallResponse> =>
    post<ToolCallResponse>('/tools/call', { name, args }),

  // 工具清单（控制台「工具」Tab）
  getTools: () => get<ToolsResponse>('/tools'),

  // ── 编排管线（P0）──
  answer: (sessionId: string, text: string) => post<ApiResponse>('/voice/answer', { session_id: sessionId, text }),
  stopTask: (sessionId: string) => post<ApiResponse>(`/task/${sessionId}/stop`),
  getEnv: () => get<{ ok: boolean; content: string }>('/env'),

  // 记忆（P1）
  getMemory: () => get<{ ok: boolean; facts: MemoryFact[] }>('/memory'),
  deleteMemory: (topic: string) => del<ApiResponse>(`/memory/${encodeURIComponent(topic)}`),

  // 定时任务（P3）
  getSchedules: () => get<{ ok: boolean; schedules: ScheduleItem[] }>('/schedules'),
  addSchedule: (cron: string, prompt: string) => post<{ ok: boolean; schedule: ScheduleItem }>('/schedules', { cron, prompt }),
  deleteSchedule: (sid: string) => del<ApiResponse>(`/schedules/${sid}`),

  // 会话历史
  getHistory: () => get<{ ok: boolean; conversations: HistoryConversation[] }>('/history'),
  getHistoryDetail: (id: string) => get<{ ok: boolean; conversation: HistoryConversationDetail }>(`/history/${encodeURIComponent(id)}`),
  deleteHistory: (id: string) => del<ApiResponse>(`/history/${encodeURIComponent(id)}`),
}

export interface MemoryFact {
  topic: string
  content: string
  source: string
  ts: string
}

export interface ScheduleItem {
  id: string
  cron: string
  prompt: string
  enabled: boolean
}

export interface HistoryConversation {
  id: string
  created: string
  updated: string
  status: string
  summary: string
  message_count: number
}

export interface HistoryMessage {
  role: string
  content: string
  tool_calls: { name: string; result?: string }[] | null
}

export interface HistoryConversationDetail extends HistoryConversation {
  messages: HistoryMessage[]
}

// ─── 编排 SSE：/api/voice/utter（唯一 agent 路径，含澄清/确认 question 事件）───

export interface UtterHandlers {
  onTaskState?: (s: TaskState) => void
  onContent?: (text: string) => void
  onReasoning?: (text: string) => void
  onToolStart?: (name: string, args: Record<string, any>) => void
  onToolEnd?: (name: string, status: string, output: string) => void
  onUsage?: (usage: TokenUsage) => void
  onQuestion?: (q: { question: string; session_id: string }) => void
  onError?: (msg: string) => void
  onDone?: (sessionId: string) => void
  /** 用户主动中止（AbortController.abort()），区别于 onError */
  onAbort?: () => void
}

/** 消费 /api/voice/utter 的 SSE 事件流；返回 session_id（供 answer/stop 用）。
 *  messages 为多轮历史种子（含当前用户消息）；signal 用于取消（对应"取消/停止"按钮）。
 *  网络错误且未收到任何事件时自动重试一次；HTTP/业务错误与流中段不重试。 */
export async function streamUtter(
  text: string,
  h: UtterHandlers,
  opts?: { messages?: { role: string; content: string }[]; signal?: AbortSignal },
): Promise<string> {
  let sessionId = ''
  const body: Record<string, unknown> = { text }
  if (opts?.messages?.length) body.messages = opts.messages
  const MAX_RETRY = 1

  /** 单次尝试：'done' = 正常/业务/中断（不重试）；'retry' = 网络错误且未收到事件（可重试）。 */
  const runOnce = async (): Promise<'done' | 'retry'> => {
    let received = false
    try {
      const resp = await fetch(`${BASE}/voice/utter`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: opts?.signal,
      })
      if (!resp.ok || !resp.body) {
        let msg = `HTTP ${resp.status}`
        try {
          const e = await resp.json()
          if (e?.error) msg = e.error
        } catch { /* not JSON */ }
        h.onError?.(msg)
        return 'done'
      }
      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        let idx: number
        while ((idx = buf.indexOf('\n\n')) !== -1) {
          const block = buf.slice(0, idx)
          buf = buf.slice(idx + 2)
          const line = block.split('\n').find(l => l.startsWith('data: '))
          if (!line) continue
          const data = line.slice(6).trim()
          if (data === '[DONE]') break
          let evt: any
          try { evt = JSON.parse(data) } catch { continue }
          received = true
          if (evt.session_id) sessionId = evt.session_id
          switch (evt.type) {
            case 'task_state': h.onTaskState?.(evt); break
            case 'content_delta': h.onContent?.(evt.text); break
            case 'reasoning_delta': h.onReasoning?.(evt.text); break
            case 'tool_start': h.onToolStart?.(evt.name, evt.args || {}); break
            case 'tool_end': h.onToolEnd?.(evt.name, evt.status, evt.output || ''); break
            case 'usage': h.onUsage?.(evt.usage); break
            case 'question': h.onQuestion?.({ question: evt.question, session_id: evt.session_id }); break
            case 'error': h.onError?.(evt.message); return 'done'
            case 'done': h.onDone?.(sessionId); return 'done'
          }
        }
      }
      h.onDone?.(sessionId)
      return 'done'
    } catch (e: any) {
      if (e?.name === 'AbortError') {
        h.onAbort?.()
        return 'done'
      }
      if (received) {
        // 流已开始后中断：提示但不重试（避免重复执行任务）
        h.onError?.('连接中断：' + (e?.message || String(e)))
        return 'done'
      }
      return 'retry'
    }
  }

  for (let i = 0; i <= MAX_RETRY; i++) {
    const status = await runOnce()
    if (status === 'done') break
    if (i === MAX_RETRY) h.onError?.('网络连接失败，请重试')
  }
  return sessionId
}
