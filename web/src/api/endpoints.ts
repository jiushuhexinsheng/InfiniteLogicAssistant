// ─── API 端点 ───
// ─── API Endpoints ───
import type { ApiResponse, ConfigResponse, DetectionReport, EditableSnapshot, LibraryTask, PingResponse, ProviderPreset, SessionItem, TextResponse, ToolCallResponse, ToolsResponse, WakeResponse } from '../types'
import { blobToWavBase64 } from '../audio'
import { get, post, patchHttp, putHttp, del } from './http'
// 类型别名（MemoryFact 等生成类型）由门面 ../api 定义，此处仅类型引用（运行时被擦除）。
// The generated type aliases (MemoryFact etc.) are defined by the ../api facade; this
// is a type-only reference (erased at runtime).
import type { MemoryFact, ScheduleItem, HistoryConversation, HistoryConversationDetail } from '../api'

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

  // 语音上传成本统计（audit 的 audio-upload via= 三前缀计数 + 近 7 日趋势；只回计数与日期）
  // Voice upload cost stats (audio-upload via= counts + 7-day trend; counts and dates only)
  /** 获取语音上传成本统计。Get voice upload cost stats. */
  getUploadStats: () => get<{
    ok: boolean
    total: number
    by_via: { wake: number; transcribe: number; 'call-segment': number }
    days: { date: string; wake: number; transcribe: number; 'call-segment': number }[]
  }>('/voice/upload-stats'),

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
