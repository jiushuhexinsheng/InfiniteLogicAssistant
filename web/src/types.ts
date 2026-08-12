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
  wake_word: WakeWordConfig
  vad: VadConfig
}

export interface TextResponse extends ApiResponse {
  text: string
}

export interface ToolCallResponse extends ApiResponse {
  status?: 'ok' | 'error'
  output?: string
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
