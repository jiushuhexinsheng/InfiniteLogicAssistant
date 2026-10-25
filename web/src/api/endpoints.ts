// ─── API 端点 ───
// ─── API Endpoints ───
import type { ApiResponse, ConfigResponse, DetectionReport, EditableSnapshot, LibraryTask, LlmModelsResponse, PingResponse, SessionItem, SetActiveModelResponse, ToolCallResponse, ToolsResponse } from '../types'
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
  /** 获取厂商模型列表。Fetch provider model list. */
  fetchModels: (section: string, profile: Record<string, any>) =>
    post<{ ok: boolean; models: string[]; count: number; error?: string }>('/providers/fetch-models', { section, profile }),
  /** 分组模型清单（对话切换器）。Grouped model catalogue for the chat picker. */
  getLlmModels: () => get<LlmModelsResponse>('/llm/models'),
  /** 设置全局 active 供应商/模型。Set the global active provider/model. */
  setActiveModel: (provider: string, model: string) =>
    post<SetActiveModelResponse>('/llm/active-model', { provider, model }),

  // 语音：音频走 /api/voice/asr/stream WebSocket；HTTP 侧只保留通话会话语义。
  // Voice: audio travels over the /api/voice/asr/stream WebSocket; HTTP keeps call-session semantics.

  // ── 通话模式（免唤醒文本判定）──
  /** 进入通话模式（建会话）。Enter call mode (open a session). */
  callStart: async (): Promise<{ ok?: boolean; open_window_s?: number; error?: string }> =>
    post('/voice/call/start'),
  /** 退出通话模式。Exit call mode. */
  callStop: async (): Promise<{ ok?: boolean; error?: string }> =>
    post('/voice/call/stop'),
  /** 通话纯文本判定（流式 ASR 已给出文本，只跑 L0/L1/L2 文本闸门）。
   *  Text-only call judging (streaming ASR already produced the text). */
  callJudge: async (text: string, meta: {
    durationMs: number; rms: number; tabFocused: boolean; inOpenWindow: boolean
  }): Promise<{ ok?: boolean; hit?: boolean; text?: string; stage?: string; reason?: string }> =>
    post('/voice/call/judge', {
      text,
      duration_ms: meta.durationMs,
      rms: meta.rms,
      tab_focused: meta.tabFocused,
      in_open_window: meta.inOpenWindow,
    }),

  // ── 本地模型与硬件能力 ──
  /** 模型列表（按能力）。Model list by capability. */
  getModels: (kind?: string) => get<{ ok: boolean; models: Record<string, any[]> }>(
    kind ? `/voice/models?kind=${encodeURIComponent(kind)}` : '/voice/models'),
  /** 刷新模型列表。Refresh the model list. */
  refreshModels: () => post<{ ok: boolean; models: Record<string, any[]> }>('/voice/models/refresh'),
  /** 硬件/引擎能力快照。Hardware/engine capability snapshot. */
  getHardware: () => get<{ ok: boolean; hardware: any }>('/voice/hardware'),
  /** 四能力当前模式与可用性。Per-capability mode and availability. */
  getCapabilities: () => get<{ ok: boolean; [key: string]: any }>('/voice/capabilities'),
  /** 某能力的参数 schema（SchemaForm 数据源；可传 model 按家族调整）。
   *  Parameter schema for one capability; pass model to vary fields by family. */
  getSchema: (kind: 'vad' | 'kws' | 'asr' | 'tts', model?: string) =>
    get<{ ok: boolean; kind: string; family: string; params: any[] }>(
      `/voice/schema?kind=${kind}${model ? `&model=${encodeURIComponent(model)}` : ''}`),
  /** 加载并实际跑一次本地引擎。Load and exercise one local engine. */
  testEngine: (kind: 'vad' | 'kws' | 'asr' | 'tts') =>
    post<{ ok: boolean; ready?: boolean; latency_ms?: number; detail?: string; error?: string }>(
      `/voice/engines/${kind}/test`),

  // 语音上传成本统计（audit 的 audio-upload via= 三前缀计数 + 近 7 日趋势；只回计数与日期）
  // Voice upload cost stats (audio-upload via= counts + 7-day trend; counts and dates only)
  /** 获取语音上传成本统计。Get voice upload cost stats. */
  getUploadStats: () => get<{
    ok: boolean
    total: number
    by_via: { stream: number }
    days: { date: string; stream: number }[]
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
  /** 暂停任务（wait / stop / force 三档，参照 DSH）。Pause the task (wait / stop / force). */
  pauseTask: (sessionId: string, mode: 'wait' | 'stop' | 'force' = 'stop') =>
    post<ApiResponse>(`/task/${sessionId}/pause`, { mode }),
  /** 恢复被暂停的任务。Resume a paused task. */
  resumeTask: (sessionId: string) => post<ApiResponse>(`/task/${sessionId}/pause/resume`),
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
