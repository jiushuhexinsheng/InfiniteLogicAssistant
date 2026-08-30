import type { components } from './api/generated'

// ─── 由后端 response_model 生成的类型（npm run gen:api 重新生成）───

export type ApiResponse = components['schemas']['ApiResponse']
export type PingResponse = components['schemas']['PingResponse']
export type ConfigResponse = components['schemas']['ConfigResponse']
export type TextResponse = components['schemas']['TextResponse']
export type WakeWordConfig = components['schemas']['WakeWordConfig']
export type VadConfig = components['schemas']['VadConfig']
export type ToolSchema = components['schemas']['ToolSchema']
export type ToolsResponse = components['schemas']['ToolsResponse']
export type ToolCallResponse = components['schemas']['ToolCallResponse']
export type ProfileConfig = components['schemas']['ProfileEditable']
export type ProviderPreset = components['schemas']['ProviderPreset']
export type EditableSnapshot = components['schemas']['EditableSnapshot']
export type DetectionIssue = components['schemas']['DetectionIssue']
export type ConnectivityResult = components['schemas']['ConnectivityResult']
export type DetectionReport = components['schemas']['DetectionReportOut']
export type SessionItem = components['schemas']['SessionOut']

// ─── SSE 事件 / 前端内部类型（不走 openapi，保留手写）───

/** OpenAI SSE usage（usage-only chunk，逐轮累计） */
export interface TokenUsage {
  prompt_tokens?: number
  completion_tokens?: number
  total_tokens?: number
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

// ─── 编排 SSE 事件（/api/voice/utter，对应后端 core/orchestrator/events.py）───

export interface TaskStateEvent {
  type: 'task_state'
  state: string
  session_id?: string
  text?: string
  status?: string
  summary?: string
  steps?: TaskStep[]
}

export interface ContentDeltaEvent {
  type: 'content_delta'
  text: string
}

export interface ReasoningDeltaEvent {
  type: 'reasoning_delta'
  text: string
}

export interface UsageEvent {
  type: 'usage'
  usage: TokenUsage
}

export interface ToolStartEvent {
  type: 'tool_start'
  name: string
  args: Record<string, any>
}

export interface ToolEndEvent {
  type: 'tool_end'
  name: string
  status: string
  output: string
}

export interface QuestionEvent {
  type: 'question'
  question: string
  session_id: string
}

export interface ErrorEvent {
  type: 'error'
  message: string
}

export interface DoneEvent {
  type: 'done'
}

export type SseEvent =
  | TaskStateEvent
  | ContentDeltaEvent
  | ReasoningDeltaEvent
  | UsageEvent
  | ToolStartEvent
  | ToolEndEvent
  | QuestionEvent
  | ErrorEvent
  | DoneEvent
