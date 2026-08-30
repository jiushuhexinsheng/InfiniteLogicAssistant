import type { ApiResponse, ConfigResponse, DetectionReport, EditableSnapshot, PingResponse, ProviderPreset, SessionItem, SseEvent, TextResponse, ToolCallResponse, TokenUsage, ToolsResponse, TaskState } from './types'
import type { components } from './api/generated'
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

async function patchHttp<T>(path: string, data?: unknown): Promise<T> {
  return request<T>(path, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: data ? JSON.stringify(data) : undefined,
  })
}

async function putHttp<T>(path: string, data?: unknown): Promise<T> {
  return request<T>(path, {
    method: 'PUT',
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

  // 设置页：可编辑快照 / 保存 / 密钥 / 检测
  getConfigFull: () => get<{ ok: boolean; editable: EditableSnapshot }>('/config/full'),
  patchConfig: (body: Record<string, any>) => patchHttp<{ ok: boolean; restart_required: boolean; error?: string }>('/config', body),
  putSecret: (path: string, value: string) => putHttp<{ ok: boolean; set: boolean; error?: string }>('/config/secrets', { path, value }),
  getDetection: () => get<{ ok: boolean; report: DetectionReport }>('/detection'),

  // 厂商目录 / 获取模型列表
  getProviders: () => get<{ ok: boolean; catalog: Record<'llm' | 'asr' | 'tts', ProviderPreset[]> }>('/providers'),
  fetchModels: (section: string, profile: Record<string, any>) =>
    post<{ ok: boolean; models: string[]; count: number; error?: string }>('/providers/fetch-models', { section, profile }),

  // 语音
  transcribe: async (blob: Blob): Promise<TextResponse> => {
    const base64Wav = await blobToWavBase64(blob)
    return post<TextResponse>('/voice/transcribe', { audio_base64: base64Wav })
  },

  // 单工具执行（前端"重试失败工具"走后端真实重跑；高风险工具需 confirm: true 显式确认）
  callTool: async (name: string, args: Record<string, any>, confirm = false): Promise<ToolCallResponse> =>
    post<ToolCallResponse>('/tools/call', { name, args, confirm }),

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
  // 会话管理（可续接对话线）
  createSession: (name?: string) => post<{ ok: boolean; session: SessionItem }>('/sessions', name ? { name } : undefined),
  listSessions: () => get<{ ok: boolean; sessions: SessionItem[] }>('/sessions'),
  renameSession: (id: string, name: string) => patchHttp<ApiResponse>(`/sessions/${encodeURIComponent(id)}`, { name }),
  deleteSession: (id: string) => del<ApiResponse>(`/sessions/${encodeURIComponent(id)}`),
}

// ─── 会话/记忆/定时类型（由后端 response_model 生成）───
export type MemoryFact = components['schemas']['FactItem']
export type ScheduleItem = components['schemas']['ScheduleItem']
export type HistoryConversation = components['schemas']['HistoryConversation']
export type HistoryMessage = components['schemas']['HistoryMessage']
export type HistoryConversationDetail = components['schemas']['HistoryConversationDetail']

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
  opts?: { messages?: { role: string; content: string }[]; signal?: AbortSignal; sessionId?: string },
): Promise<string> {
  let sessionId = ''
  const body: Record<string, unknown> = { text }
  if (opts?.messages?.length) body.messages = opts.messages
  if (opts?.sessionId) body.session_id = opts.sessionId
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
          let evt: SseEvent
          try { evt = JSON.parse(data) as SseEvent } catch { continue }
          received = true
          switch (evt.type) {
            case 'task_state':
              if (evt.session_id) sessionId = evt.session_id
              h.onTaskState?.(evt)
              break
            case 'content_delta': h.onContent?.(evt.text); break
            case 'reasoning_delta': h.onReasoning?.(evt.text); break
            case 'tool_start': h.onToolStart?.(evt.name, evt.args || {}); break
            case 'tool_end': h.onToolEnd?.(evt.name, evt.status, evt.output || ''); break
            case 'usage': h.onUsage?.(evt.usage); break
            case 'question':
              if (evt.session_id) sessionId = evt.session_id
              h.onQuestion?.({ question: evt.question, session_id: evt.session_id })
              break
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
