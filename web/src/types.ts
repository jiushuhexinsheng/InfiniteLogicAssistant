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
  wake_word: WakeWordConfig
  vad: VadConfig
}

export interface TextResponse extends ApiResponse {
  text: string
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
