export interface ApiResponse {
  ok: boolean
  error?: string
}

export interface PingResponse extends ApiResponse {
  time: string
}

export interface ConfigResponse extends ApiResponse {
  llm_available: boolean
  llm_profile: string
  asr_available: boolean
  asr_profile: string
  tts_available: boolean
  tts_profile: string
  tts_voice?: string
  tts_model?: string
  wake_word: WakeWordConfig
  vad: VadConfig
}

export interface TextResponse extends ApiResponse {
  text: string
}

export interface ToolCallResponse extends ApiResponse {
  status?: 'ok' | 'error'
  output?: string
  needs_confirm?: boolean
}

/** OpenAI SSE usage（usage-only chunk，逐轮累计） */
export interface TokenUsage {
  prompt_tokens?: number
  completion_tokens?: number
  total_tokens?: number
}

export interface ToolSchema {
  type: string
  function: {
    name: string
    description: string
    parameters: {
      type: string
      properties: Record<string, any>
      required?: string[]
    }
  }
}

export interface ToolsResponse extends ApiResponse {
  tools: ToolSchema[]
}

export interface TaskStep {
  step: number
  tool: string
  args: Record<string, any>
  status: string
  result: string
}

export interface TaskState {
  state: string
  status?: string
  summary?: string
  steps?: TaskStep[]
  session_id?: string
}

export interface WakeWordConfig {
  enabled: boolean
  keyword: string
  sensitivity: number
  model_path: string
}

export interface VadConfig {
  silence_threshold: number
  silence_duration_ms: number
  max_duration_ms: number
}

/** 工具时间轴步骤（ToolTimeline 数据源） */
export interface ToolStep {
  id: string
  name: string
  icon?: string
  status: 'queued' | 'running' | 'done' | 'failed'
  durationMs?: number
  args?: Record<string, any>
  result?: string
}

// ─── 设置页：可编辑配置快照（/api/config/full）与检测（/api/detection） ───

export interface ProfileConfig {
  provider?: string
  vendor?: string
  endpoint?: string
  model?: string
  vision_model?: string
  chat_path?: string
  max_tokens?: number
  temperature?: number
  timeout?: number
  language?: string
  voice?: string
  format?: string
  api_key_env?: string
  models?: string[]
  models_path?: string
  voices?: string[]
  compat?: Record<string, any>
}

/** 厂商目录预设（GET /api/providers，已剥密钥） */
export interface ProviderPreset {
  id: string
  kind: 'llm' | 'asr' | 'tts'
  label: string
  provider: string
  endpoint: string
  chat_path: string
  models_path?: string
  models: string[]
  vision_models: string[]
  voices: string[]
  api_key_env: string
  compat: Record<string, any>
  defaults: Record<string, any>
}

export interface SectionEditable<T> {
  active: string
  profiles: Record<string, T>
  api_key_set: Record<string, boolean>
}

export interface EditableSnapshot {
  llm: SectionEditable<ProfileConfig>
  asr: SectionEditable<ProfileConfig>
  tts: SectionEditable<ProfileConfig> & { enabled: boolean }
  wake_word: WakeWordConfig
  vad: VadConfig
  agent: { recursion_limit: number; multi_agent: boolean }
  llm_client: {
    retry_max: number; retry_backoff_base: number; retry_backoff_max: number
    circuit_breaker_threshold: number; circuit_breaker_cooldown: number; request_timeout: number
  }
  tools: { search_max_results: number; weather_timeout: number }
  mcp: { servers: { name: string; command: string; args: string[] }[] }
  rag: { auto_index: boolean }
  server: {
    host: string; port: number; open_browser: boolean
    cors_origins: string[]; api_token_set: boolean
  }
}

export interface DetectionIssue {
  level: 'error' | 'warning' | 'info'
  key: string
  message: string
}

export interface ConnectivityResult {
  name: string
  status: 'ok' | 'skip' | 'fail'
  latency_ms: number | null
  detail: string
}

export interface DetectionReport {
  environment: Record<string, any>
  config: { ok: boolean; issues: DetectionIssue[] }
  connectivity: ConnectivityResult[]
}
