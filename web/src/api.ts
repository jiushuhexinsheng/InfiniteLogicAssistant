/**
 * API 模块 - 封装与后端的所有 HTTP 通信
 * API Module - Encapsulates all HTTP communication with the backend
 */
import type { ApiResponse, ConfigResponse, DetectionReport, EditableSnapshot, PingResponse, ProviderPreset, QuestionEvent, QuestionOption, SessionItem, SseEvent, TextResponse, ToolCallResponse, TokenUsage, ToolsResponse, TaskState } from './types'
import type { components } from './api/generated'
import { blobToWavBase64 } from './audio'
import { formatError } from './errors'

// ─── HTTP 封装 / HTTP Wrappers ───

/** API 基础路径 */
/** API base path */
const BASE = '/api'

/**
 * 通用 HTTP 请求函数，处理响应和错误
 * Generic HTTP request function that handles responses and errors
 * @param path - API 路径 / API path
 * @param options - fetch 请求选项 / fetch request options
 * @returns Promise<T> - 解析后的 JSON 响应 / Parsed JSON response
 */
async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, options)
  if (!res.ok) {
    // 尝试解析 JSON 错误体，失败则用 HTTP 状态码
    // Try to parse JSON error body, fallback to HTTP status code
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

/** GET 请求封装。GET request wrapper. */
async function get<T>(path: string): Promise<T> {
  return request<T>(path)
}

/** POST 请求封装。POST request wrapper. */
async function post<T>(path: string, data?: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: data ? JSON.stringify(data) : undefined,
  })
}

/** PATCH 请求封装。PATCH request wrapper. */
async function patchHttp<T>(path: string, data?: unknown): Promise<T> {
  return request<T>(path, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: data ? JSON.stringify(data) : undefined,
  })
}

/** PUT 请求封装。PUT request wrapper. */
async function putHttp<T>(path: string, data?: unknown): Promise<T> {
  return request<T>(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: data ? JSON.stringify(data) : undefined,
  })
}

/** DELETE 请求封装。DELETE request wrapper. */
async function del<T>(path: string): Promise<T> {
  return request<T>(path, { method: 'DELETE' })
}

// ─── API 端点 ───
// ─── API Endpoints ───

/**
 * API 端点集合，封装所有后端接口调用
 * Collection of API endpoints that encapsulate all backend API calls
 */
export const api = {
  /** Ping 检查服务状态。Ping to check service status. */
  ping: () => get<PingResponse>('/ping'),
  /** 获取配置。Get configuration. */
  getConfig: () => get<ConfigResponse>('/config'),

  // 设置页：可编辑快照 / 保存 / 密钥 / 检测
  // Settings page: editable snapshot / save / secrets / detection
  /** 获取完整配置（含可编辑快照）。Get full config (with editable snapshot). */
  getConfigFull: () => get<{ ok: boolean; editable: EditableSnapshot }>('/config/full'),
  /** 更新配置。Update configuration. */
  patchConfig: (body: Record<string, any>) => patchHttp<{ ok: boolean; restart_required: boolean; error?: string }>('/config', body),
  /** 设置密钥。Set secret. */
  putSecret: (path: string, value: string) => putHttp<{ ok: boolean; set: boolean; error?: string }>('/config/secrets', { path, value }),
  /** 获取检测报告。Get detection report. */
  getDetection: () => get<{ ok: boolean; report: DetectionReport }>('/detection'),

  // 厂商目录 / 获取模型列表
  // Provider catalog / fetch model list
  /** 获取厂商目录。Get provider catalog. */
  getProviders: () => get<{ ok: boolean; catalog: Record<'llm' | 'asr' | 'tts', ProviderPreset[]> }>('/providers'),
  /** 获取厂商模型列表。Fetch provider model list. */
  fetchModels: (section: string, profile: Record<string, any>) =>
    post<{ ok: boolean; models: string[]; count: number; error?: string }>('/providers/fetch-models', { section, profile }),

  // 语音
  // Voice
  /** 语音转文字。Speech to text. */
  transcribe: async (blob: Blob): Promise<TextResponse> => {
    const base64Wav = await blobToWavBase64(blob)
    return post<TextResponse>('/voice/transcribe', { audio_base64: base64Wav })
  },

  // 单工具执行（前端"重试失败工具"走后端真实重跑；高风险工具需 confirm: true 显式确认）
  // Single tool execution (frontend "retry failed tool" runs backend real retry; high-risk tools need confirm: true explicit confirmation)
  /** 调用单个工具。Call a single tool. */
  callTool: async (name: string, args: Record<string, any>, confirm = false): Promise<ToolCallResponse> =>
    post<ToolCallResponse>('/tools/call', { name, args, confirm }),

  // 工具清单（控制台「工具」Tab）
  // Tool list (Console "Tools" Tab)
  /** 获取工具清单。Get tools list. */
  getTools: () => get<ToolsResponse>('/tools'),

  // ── 编排管线（P0）──
  // ── Orchestration Pipeline (P0) ──
  /** 发送回答。Send answer. */
  answer: (sessionId: string, text: string, choice?: string) =>
    post<ApiResponse>('/voice/answer', choice ? { session_id: sessionId, text, choice } : { session_id: sessionId, text }),
  /** 停止任务。Stop task. */
  stopTask: (sessionId: string) => post<ApiResponse>(`/task/${sessionId}/stop`),
  /** 获取环境变量。Get environment variables. */
  getEnv: () => get<{ ok: boolean; content: string }>('/env'),

  // 记忆（P1）
  // Memory (P1)
  /** 获取记忆事实。Get memory facts. */
  getMemory: () => get<{ ok: boolean; facts: MemoryFact[] }>('/memory'),
  /** 删除记忆。Delete memory. */
  deleteMemory: (topic: string) => del<ApiResponse>(`/memory/${encodeURIComponent(topic)}`),

  // 定时任务（P3）
  // Scheduled Tasks (P3)
  /** 获取定时任务列表。Get scheduled tasks list. */
  getSchedules: () => get<{ ok: boolean; schedules: ScheduleItem[] }>('/schedules'),
  /** 添加定时任务。Add scheduled task. */
  addSchedule: (cron: string, prompt: string) => post<{ ok: boolean; schedule: ScheduleItem }>('/schedules', { cron, prompt }),
  /** 删除定时任务。Delete scheduled task. */
  deleteSchedule: (sid: string) => del<ApiResponse>(`/schedules/${sid}`),

  // 会话历史
  // Session History
  /** 获取会话历史列表。Get session history list. */
  getHistory: () => get<{ ok: boolean; conversations: HistoryConversation[] }>('/history'),
  /** 获取会话历史详情。Get session history detail. */
  getHistoryDetail: (id: string) => get<{ ok: boolean; conversation: HistoryConversationDetail }>(`/history/${encodeURIComponent(id)}`),
  /** 删除会话历史。Delete session history. */
  deleteHistory: (id: string) => del<ApiResponse>(`/history/${encodeURIComponent(id)}`),
  // 会话管理（可续接对话线）
  // Session Management (resumable conversation threads)
  /** 创建新会话。Create new session. */
  createSession: (name?: string) => post<{ ok: boolean; session: SessionItem }>('/sessions', name ? { name } : undefined),
  /** 获取会话列表。Get session list. */
  listSessions: (archived?: boolean) => get<{ ok: boolean; sessions: SessionItem[] }>(archived ? '/sessions?archived=true' : '/sessions'),
  /** 重命名会话。Rename session. */
  renameSession: (id: string, name: string) => patchHttp<ApiResponse>(`/sessions/${encodeURIComponent(id)}`, { name }),
  /** 归档/取消归档会话。Archive/unarchive session. */
  archiveSession: (id: string, archived: boolean) => patchHttp<ApiResponse>(`/sessions/${encodeURIComponent(id)}`, { archived }),
  /** 清空会话消息。Clear session messages. */
  clearSession: (id: string) => post<ApiResponse>(`/sessions/${encodeURIComponent(id)}/clear`),
  /** 删除会话。Delete session. */
  deleteSession: (id: string) => del<ApiResponse>(`/sessions/${encodeURIComponent(id)}`),
}

// ─── 会话/记忆/定时类型（由后端 response_model 生成）───
// ─── Session/Memory/Schedule Types (generated from backend response_model) ───

/** 记忆事实类型。Memory fact type. */
export type MemoryFact = components['schemas']['FactItem']
/** 定时任务项类型。Schedule item type. */
export type ScheduleItem = components['schemas']['ScheduleItem']
/** 会话历史对话类型。History conversation type. */
export type HistoryConversation = components['schemas']['HistoryConversation']
/** 会话历史消息类型。History message type. */
export type HistoryMessage = components['schemas']['HistoryMessage']
/** 会话历史详情类型。History conversation detail type. */
export type HistoryConversationDetail = components['schemas']['HistoryConversationDetail']

// ─── 编排 SSE：/api/voice/utter（唯一 agent 路径，含澄清/确认 question 事件）───
// ─── Orchestration SSE: /api/voice/utter (sole agent path, includes clarification/confirmation question events) ───

/**
 * Utter SSE 事件处理器接口
 * Utter SSE event handler interface
 */
export interface UtterHandlers {
  /** 任务状态变化回调。Task state change callback. */
  onTaskState?: (s: TaskState) => void
  /** 内容增量回调。Content delta callback. */
  onContent?: (text: string) => void
  /** 推理过程增量回调。Reasoning delta callback. */
  onReasoning?: (text: string) => void
  /** 工具开始执行回调。Tool start callback. */
  onToolStart?: (name: string, args: Record<string, any>) => void
  /** 工具执行结束回调。Tool end callback. */
  onToolEnd?: (name: string, status: string, output: string) => void
  /** Token 使用量回调。Token usage callback. */
  onUsage?: (usage: TokenUsage) => void
  /** 问题事件回调（澄清/确认）。Question event callback (clarification/confirmation). */
  onQuestion?: (q: { question: string; session_id: string; kind: QuestionEvent['kind']; options: QuestionOption[] }) => void
  /** 错误回调。Error callback. */
  onError?: (msg: string) => void
  /** 完成回调。Done callback. */
  onDone?: (sessionId: string) => void
  /** 用户主动中止（AbortController.abort()），区别于 onError */
  /** User initiated abort (AbortController.abort()), distinct from onError */
  onAbort?: () => void
}

/**
 * 消费 /api/voice/utter 的 SSE 事件流；返回 session_id（供 answer/stop 用）。
 * Consume SSE event stream from /api/voice/utter; returns session_id (for answer/stop use).
 * messages 为多轮历史种子（含当前用户消息）；signal 用于取消（对应"取消/停止"按钮）。
 * messages is multi-turn history seed (including current user message); signal is used for cancellation (corresponds to "cancel/stop" button).
 * 网络错误且未收到任何事件时自动重试一次；HTTP/业务错误与流中段不重试。
 * Auto-retry once on network error without any events received; no retry on HTTP/business errors or mid-stream interruption.
 * @param text - 用户输入文本 / User input text
 * @param h - 事件处理器 / Event handlers
 * @param opts - 可选参数 / Optional parameters
 * @returns Promise<string> - session_id
 */
export async function streamUtter(
  text: string,
  h: UtterHandlers,
  opts?: { messages?: { role: string; content: string }[]; signal?: AbortSignal; sessionId?: string; mode?: string },
): Promise<string> {
  let sessionId = ''
  const body: Record<string, unknown> = { text }
  if (opts?.messages?.length) body.messages = opts.messages
  if (opts?.sessionId) body.session_id = opts.sessionId
  // 助手模式随请求下发（后端据此决定完成后是否询问并存档）。
  // The assistant mode travels with the request (the backend uses it to decide whether to
  // ask and archive on completion).
  if (opts?.mode) body.mode = opts.mode
  const MAX_RETRY = 1

  /**
   * 单次尝试：'done' = 正常/业务/中断（不重试）；'retry' = 网络错误且未收到事件（可重试）。
   * Single attempt: 'done' = normal/business/interrupt (no retry); 'retry' = network error without events received (retryable).
   * @returns Promise<'done' | 'retry'>
   */
  const runOnce = async (): Promise<'done' | 'retry'> => {
    // 标记是否已接收到事件 / Flag indicating if any event has been received
    let received = false
    try {
      // 发起 POST 请求到 /api/voice/utter / Initiate POST request to /api/voice/utter
      const resp = await fetch(`${BASE}/voice/utter`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: opts?.signal,
      })
      // 处理 HTTP 错误响应 / Handle HTTP error responses
      if (!resp.ok || !resp.body) {
        let msg = `HTTP ${resp.status}`
        try {
          const e = await resp.json()
          if (e?.error) msg = e.error
        } catch { /* not JSON */ }
        h.onError?.(msg)
        return 'done'
      }
      // 获取响应流读取器 / Get response stream reader
      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      // 读取 SSE 事件流 / Read SSE event stream
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        // 解码二进制数据为文本 / Decode binary data to text
        buf += decoder.decode(value, { stream: true })
        let idx: number
        // 解析 SSE 事件块（以 \n\n 分隔）/ Parse SSE event blocks (separated by \n\n)
        while ((idx = buf.indexOf('\n\n')) !== -1) {
          const block = buf.slice(0, idx)
          buf = buf.slice(idx + 2)
          // 查找 data: 行 / Find data: line
          const line = block.split('\n').find(l => l.startsWith('data: '))
          if (!line) continue
          // 提取 JSON 数据 / Extract JSON data
          const data = line.slice(6).trim()
          if (data === '[DONE]') break
          // 解析 JSON 事件数据 / Parse JSON event data
          let evt: SseEvent
          try { evt = JSON.parse(data) as SseEvent } catch { continue }
          // 标记已接收到事件 / Mark event as received
          received = true
          // 根据事件类型分发处理 / Dispatch handling based on event type
          switch (evt.type) {
            case 'task_state':
              // 任务状态变化，更新 session_id / Task state change, update session_id
              if (evt.session_id) sessionId = evt.session_id
              h.onTaskState?.(evt)
              break
            // 内容增量事件 / Content delta event
            case 'content_delta': h.onContent?.(evt.text); break
            // 推理过程增量事件 / Reasoning delta event
            case 'reasoning_delta': h.onReasoning?.(evt.text); break
            // 工具开始执行事件 / Tool start event
            case 'tool_start': h.onToolStart?.(evt.name, evt.args || {}); break
            // 工具执行结束事件 / Tool end event
            case 'tool_end': h.onToolEnd?.(evt.name, evt.status, evt.output || ''); break
            // Token 使用量事件 / Token usage event
            case 'usage': h.onUsage?.(evt.usage); break
            // 问题事件（澄清/确认）/ Question event (clarification/confirmation)
            case 'question':
              if (evt.session_id) sessionId = evt.session_id
              h.onQuestion?.({ question: evt.question, session_id: evt.session_id, kind: evt.kind, options: evt.options })
              break
            // 错误事件，终止处理 / Error event, terminate processing
            case 'error': h.onError?.(evt.message); return 'done'
            // 完成事件，正常结束 / Done event, normal termination
            case 'done': h.onDone?.(sessionId); return 'done'
          }
        }
      }
      // 正常完成 / Normal completion
      h.onDone?.(sessionId)
      return 'done'
    } catch (e: any) {
      // 用户主动中止 / User initiated abort
      if (e?.name === 'AbortError') {
        h.onAbort?.()
        return 'done'
      }
      if (received) {
        // 流已开始后中断：提示但不重试（避免重复执行任务）
        // Interrupted after stream started: notify but don't retry (avoid duplicate task execution)
        h.onError?.('连接中断：' + formatError(e))
        return 'done'
      }
      // 网络错误且未收到事件，可重试 / Network error without events received, retryable
      return 'retry'
    }
  }

  // 重试循环，最多 MAX_RETRY 次 / Retry loop, up to MAX_RETRY times
  for (let i = 0; i <= MAX_RETRY; i++) {
    const status = await runOnce()
    if (status === 'done') break
    if (i === MAX_RETRY) h.onError?.('网络连接失败，请重试')
  }
  return sessionId
}
