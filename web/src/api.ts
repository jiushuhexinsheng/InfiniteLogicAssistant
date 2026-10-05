/**
 * API 模块 - 封装与后端的所有 HTTP 通信
 * API Module - Encapsulates all HTTP communication with the backend
 */
import type { ApiResponse, ConfigResponse, DetectionReport, EditableSnapshot, LibraryTask, PingResponse, ProviderPreset, QuestionEvent, QuestionOption, SessionItem, SseEvent, TextResponse, ToolCallResponse, TokenUsage, ToolsResponse, TaskState, WakeResponse } from './types'
import type { components } from './api/generated'
import { blobToWavBase64 } from './audio'
// （streamUtter 断线文案已改为 resume 流程的固定提示，docs/designs/06 —— 不再内嵌底层错误。）
// (streamUtter's disconnect wording is now a fixed resume-flow notice,
// docs/designs/06 — the underlying error is no longer embedded.)

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

  // 唤醒检测：转写 + 唤醒词判定 + 指令切分（后端完成判定，前端只需照结果行事）。
  // Wake detection: transcribe, judge the wake word, split out the command. The backend owns the
  // judgement; the frontend only acts on the result.
  /** 唤醒检测。Wake detection. */
  /** 本地 KWS 快检：只回答「有没有唤醒词」，毫秒级、不出本机、零云端调用。
   *  Local KWS quick check: only "is the wake word present" — milliseconds, no cloud call. */
  wakeCheck: async (blob: Blob): Promise<{ ok?: boolean; hit?: boolean; bypass?: boolean; error?: string }> => {
    const base64Wav = await blobToWavBase64(blob)
    return post<{ ok?: boolean; hit?: boolean; bypass?: boolean; error?: string }>('/voice/wake/check', { audio_base64: base64Wav })
  },
  wakeDetect: async (blob: Blob, opts?: { mode?: string }): Promise<WakeResponse> => {
    const base64Wav = await blobToWavBase64(blob)
    // mode 随请求下发：cloud 显式旁路后端 KWS 闸门（纯云端判定，最大召回）
    // The mode travels with the request: cloud explicitly bypasses the backend KWS
    // gate (pure cloud judging, maximum recall).
    return post<WakeResponse>('/voice/wake', { audio_base64: base64Wav, ...(opts?.mode ? { mode: opts.mode } : {}) })
  },

  // ── 通话模式（免唤醒三级漏斗）──
  /** 进入通话模式（建会话）。Enter call mode (open a session). */
  callStart: async (): Promise<{ ok?: boolean; open_window_s?: number; error?: string }> =>
    post('/voice/call/start'),
  /** 退出通话模式。Exit call mode. */
  callStop: async (): Promise<{ ok?: boolean; error?: string }> =>
    post('/voice/call/stop'),
  /** 段落进漏斗：hit 才把 text 送编排。Segment into the funnel; on hit the text goes to the orchestrator. */
  callSegment: async (blob: Blob, meta: { tabFocused: boolean; inOpenWindow: boolean }): Promise<{ ok?: boolean; hit?: boolean; text?: string; stage?: string; reason?: string }> => {
    const audio_base64 = await blobToWavBase64(blob)
    return post('/voice/call/segment', { audio_base64, tab_focused: meta.tabFocused, in_open_window: meta.inOpenWindow })
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
  /** 发送回答（qid 供问答配对/陈旧拒收；source 标记作答通道）。
   *  Send answer (qid pairs answers / rejects stale ones; source marks the channel). */
  answer: (sessionId: string, text: string, choice?: string, opts?: { qid?: string; source?: string }) => {
    const body: Record<string, unknown> = { session_id: sessionId, text }
    if (choice) body.choice = choice
    if (opts?.qid) body.qid = opts.qid
    if (opts?.source) body.source = opts.source
    return post<ApiResponse>('/voice/answer', body)
  },
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

  // 任务库（P7）
  // Task library (P7)
  /** 任务库：列出存档的成功任务。Task library: list archived successful tasks. */
  listLibrary: () => get<{ ok: boolean; tasks: LibraryTask[] }>('/library'),
  /** 任务库：取单条详情。Task library: fetch one archived task. */
  getLibraryTask: (id: number) => get<{ ok: boolean; task: LibraryTask }>(`/library/${id}`),
  /** 任务库：删除一条。Task library: delete one archived task. */
  deleteLibraryTask: (id: number) => del<ApiResponse>(`/library/${id}`),

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
  /** 分叉会话前缀为新会话（docs/designs/07；源会话只读不动）。
   *  Fork a session prefix into a new conversation (docs/designs/07; source untouched). */
  forkSession: (id: string, upTo: number) =>
    post<{ ok: boolean; session: SessionItem & { messages?: unknown[] } }>(
      `/sessions/${encodeURIComponent(id)}/fork`, { up_to: upTo }),
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
  /** 原始事件通配回调（块 reducer 用，先于具体分发回调触发）。
   *  Wildcard raw-event callback (for the block reducer; fires before the specific handlers). */
  onEvent?: (ev: SseEvent) => void
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
  onQuestion?: (q: { question: string; session_id: string; kind: QuestionEvent['kind']; options: QuestionOption[]; qid?: string }) => void
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

  // ── seq 游标与断线恢复（docs/designs/06）──
  // lastSeq：已消费的最大事件序号（服务端回放 seq≤lastSeq 的帧会被跳过 —— 重连不重复）。
  // Last consumed event seq (frames replayed with seq ≤ lastSeq are skipped — no
  // duplicates across reconnects).
  let lastSeq = 0
  let everReceived = false
  const MAX_RETRY = 1          // 主连接零事件重试（旧语义保留）。Main-conn zero-event retry (legacy).
  const RESUME_RETRY = 2       // resume 重试次数（退避 1s/3s）。Resume attempts (backoff 1s/3s).
  const PING_TIMEOUT_MS = 35000 // 35s 无任何帧（含 ping）判死。No frame (incl. ping) for 35s = dead.
  const sleep = (ms: number) => new Promise<void>(r => setTimeout(r, ms))

  /** 消费一条连接：分发事件（seq 去重 + ping 看门狗），返回结局。
   *  'closed' = 正常/业务错误/中止（收工）；'network' = 连接断了（可 resume）。
   *
   *  Consume one connection: dispatch events (seq dedup + ping watchdog) and return
   *  the outcome — 'closed' = normal/business error/abort (finished); 'network' =
   *  connection lost (resumable). */
  const consume = async (resp: Response): Promise<'closed' | 'network'> => {
    const reader = resp.body!.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    let timedOut = false
    let finished = false
    try {
      while (true) {
        // 看门狗：超时 cancel 读取器 → read() 立刻返回 → 按断线处理。
        // Watchdog: cancel the reader on timeout → read() returns at once → network loss.
        const timer = setTimeout(() => {
          timedOut = true
          try { void reader.cancel() } catch { /* ignore */ }
        }, PING_TIMEOUT_MS)
        let chunk: ReadableStreamReadResult<Uint8Array>
        try {
          chunk = await reader.read()
        } finally {
          clearTimeout(timer)
        }
        if (chunk.done) break
        buf += decoder.decode(chunk.value, { stream: true })
        let idx: number
        while ((idx = buf.indexOf('\n\n')) !== -1) {
          const block = buf.slice(0, idx)
          buf = buf.slice(idx + 2)
          const line = block.split('\n').find(l => l.startsWith('data: '))
          if (!line) continue
          const data = line.slice(6).trim()
          if (data === '[DONE]') continue
          let evt: any
          try { evt = JSON.parse(data) } catch { continue }
          // 心跳：只重置看门狗，不进分发、无 seq（docs/designs/06）。
          // Heartbeat: resets the watchdog only — not dispatched, carries no seq.
          if (evt.type === 'ping') continue
          // 回放去重：seq 在游标内（重连重发的旧帧）直接丢。
          // Replay dedup: a seq behind the cursor (an old frame resent on reconnect) is dropped.
          if (typeof evt.seq === 'number') {
            if (evt.seq <= lastSeq) continue
            lastSeq = evt.seq
          }
          everReceived = true
          // 原始事件先交通配回调（块 reducer 归一），再走具体分发
          // Raw events go to the wildcard callback (block reducer) first, then the specific dispatch
          h.onEvent?.(evt)
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
              h.onQuestion?.({ question: evt.question, session_id: evt.session_id, kind: evt.kind, options: evt.options, qid: evt.qid })
              break
            case 'error': h.onError?.(evt.message); finished = true; return 'closed'
            case 'done': h.onDone?.(sessionId); finished = true; return 'closed'
          }
        }
      }
      if (timedOut) return 'network'   // 看门狗杀读 → 断线。Watchdog killed the read → network loss.
      if (!finished) h.onDone?.(sessionId)  // 服务端正常收流但没发 done（防御）。Stream ended without done (defensive).
      return 'closed'
    } catch (e: any) {
      if (e?.name === 'AbortError') { h.onAbort?.(); return 'closed' }
      if (timedOut) return 'network'
      return 'network'
    }
  }

  /** 打开一条连接：utter（首连/零事件重试）或 resume。Open one connection. */
  const open = async (mode: 'main' | 'resume'): Promise<Response> => {
    if (mode === 'main') {
      return fetch(`${BASE}/voice/utter`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: opts?.signal,
      })
    }
    return fetch(`${BASE}/voice/resume`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId || opts?.sessionId || '', last_seq: lastSeq }),
      signal: opts?.signal,
    })
  }

  let mainTry = 0
  let resumeTry = 0
  let mode: 'main' | 'resume' = 'main'
  // 重连退避：第 1 次 1s、第 2 次 3s（docs/designs/06 §批2）。
  const RESUME_BACKOFF = [1000, 3000]
  for (;;) {
    let resp: Response
    try {
      resp = await open(mode)
    } catch (e: any) {
      if (e?.name === 'AbortError') { h.onAbort?.(); return sessionId }
      if (mode === 'main' && !everReceived && mainTry < MAX_RETRY) { mainTry++; continue }
      if (mode === 'resume' && resumeTry < RESUME_RETRY) {
        await sleep(RESUME_BACKOFF[Math.min(resumeTry, RESUME_BACKOFF.length - 1)])
        resumeTry++
        continue
      }
      h.onError?.(mode === 'main' ? '网络连接失败，请重试' : '连接中断：任务已在服务端继续，稍后刷新历史查看')
      return sessionId
    }
    if (!resp.ok || !resp.body) {
      let msg = `HTTP ${resp.status}`
      try {
        const e = await resp.json()
        if (e?.error) msg = e.error
      } catch { /* not JSON */ }
      if (mode === 'main' && resp.status !== 200) { h.onError?.(msg); return sessionId }
      if (mode === 'resume') {
        // 404 no_run = 运行已结束/不存在 → 历史重载兜底（调用方刷新）。
        if (resp.status === 404) { h.onError?.('连接中断，回合已结束：请刷新历史查看'); return sessionId }
        if (resumeTry < RESUME_RETRY) { await sleep(RESUME_BACKOFF[Math.min(resumeTry, 2 - 1)]); resumeTry++; mode = 'resume'; continue }
        h.onError?.(msg); return sessionId
      }
      h.onError?.(msg)
      return sessionId
    }
    const outcome = await consume(resp)
    if (outcome === 'closed') return sessionId
    // 断线（网络错/看门狗）→ 进入 resume（服务端宽限期内任务仍在跑）。
    // Network loss → resume (the server keeps the task alive inside its grace window).
    if (opts?.signal?.aborted) { h.onAbort?.(); return sessionId }
    mode = 'resume'
    resumeTry = 0
    if (!sessionId && !opts?.sessionId) { h.onError?.('连接中断且无会话标识，无法恢复'); return sessionId }
    await sleep(RESUME_BACKOFF[0])
    resumeTry = 1   // 首次重连已消费掉 1s 退避额度。The first reconnect spends the 1s slot.
  }
}
