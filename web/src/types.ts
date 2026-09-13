/**
 * 类型定义模块
 * Type definitions module
 */
import type { components } from './api/generated'

// ─── 由后端 response_model 生成的类型（npm run gen:api 重新生成）───
// ─── Types generated from backend response_model (regenerate with npm run gen:api) ───

/** API 通用响应类型。API common response type. */
export type ApiResponse = components['schemas']['ApiResponse']
/** Ping 响应类型。Ping response type. */
export type PingResponse = components['schemas']['PingResponse']
/** 配置响应类型。Configuration response type. */
export type ConfigResponse = components['schemas']['ConfigResponse']
/** 文本响应类型。Text response type. */
export type TextResponse = components['schemas']['TextResponse']
/** 唤醒词配置类型。Wake word config type. */
export type WakeWordConfig = components['schemas']['WakeWordConfig']
/** VAD 配置类型。VAD config type. */
export type VadConfig = components['schemas']['VadConfig']
/** 工具 Schema 类型。Tool schema type. */
export type ToolSchema = components['schemas']['ToolSchema']
/** 工具列表响应类型。Tools list response type. */
export type ToolsResponse = components['schemas']['ToolsResponse']
/** 工具调用响应类型。Tool call response type. */
export type ToolCallResponse = components['schemas']['ToolCallResponse']
/** 配置文件类型。Profile config type. */
export type ProfileConfig = components['schemas']['ProfileEditable']
/** 厂商预设类型。Provider preset type. */
export type ProviderPreset = components['schemas']['ProviderPreset']
/** 可编辑快照类型。Editable snapshot type. */
export type EditableSnapshot = components['schemas']['EditableSnapshot']
/** 检测问题类型。Detection issue type. */
export type DetectionIssue = components['schemas']['DetectionIssue']
/** 连接结果类型。Connectivity result type. */
export type ConnectivityResult = components['schemas']['ConnectivityResult']
/** 检测报告类型。Detection report type. */
export type DetectionReport = components['schemas']['DetectionReportOut']
/** 会话项类型。Session item type. */
export type SessionItem = components['schemas']['SessionOut']

// ─── SSE 事件 / 前端内部类型（不走 openapi，保留手写）───
// ─── SSE Events / Frontend internal types (not from openapi, manually maintained) ───

/**
 * OpenAI SSE usage（usage-only chunk，逐轮累计）
 * OpenAI SSE usage (usage-only chunk, accumulated per turn)
 */
export interface TokenUsage {
  /** 提示词 token 数。Prompt tokens count. */
  prompt_tokens?: number
  /** 完成词 token 数。Completion tokens count. */
  completion_tokens?: number
  /** 总 token 数。Total tokens count. */
  total_tokens?: number
}

/**
 * 任务步骤接口
 * Task step interface
 */
export interface TaskStep {
  /** 步骤编号。Step number. */
  step: number
  /** 工具名称。Tool name. */
  tool: string
  /** 工具参数。Tool arguments. */
  args: Record<string, any>
  /** 步骤状态。Step status. */
  status: string
  /** 步骤结果。Step result. */
  result: string
}

/**
 * 任务状态接口
 * Task state interface
 */
export interface TaskState {
  /** 任务状态。Task state. */
  state: string
  /** 状态描述。Status description. */
  status?: string
  /** 任务摘要。Task summary. */
  summary?: string
  /** 任务步骤列表。Task steps list. */
  steps?: TaskStep[]
  /** 会话 ID。Session ID. */
  session_id?: string
}

/**
 * 工具时间轴步骤（ToolTimeline 数据源）
 * Tool timeline step (ToolTimeline data source)
 */
export interface ToolStep {
  /** 步骤 ID。Step ID. */
  id: string
  /** 工具名称。Tool name. */
  name: string
  /** 工具图标。Tool icon. */
  icon?: string
  /** 步骤状态。Step status. */
  status: 'queued' | 'running' | 'done' | 'failed'
  /** 持续时间（毫秒）。Duration in milliseconds. */
  durationMs?: number
  /** 工具参数。Tool arguments. */
  args?: Record<string, any>
  /** 步骤结果。Step result. */
  result?: string
}

// ─── 编排 SSE 事件（/api/voice/utter，对应后端 core/orchestrator/events.py）───
// ─── Orchestration SSE Events (/api/voice/utter, corresponds to backend core/orchestrator/events.py) ───

/**
 * 任务状态变化事件
 * Task state change event
 */
export interface TaskStateEvent {
  /** 事件类型。Event type. */
  type: 'task_state'
  /** 任务状态。Task state. */
  state: string
  /** 会话 ID。Session ID. */
  session_id?: string
  /** 文本内容。Text content. */
  text?: string
  /** 状态描述。Status description. */
  status?: string
  /** 任务摘要。Task summary. */
  summary?: string
  /** 任务步骤列表。Task steps list. */
  steps?: TaskStep[]
}

/**
 * 内容增量事件
 * Content delta event
 */
export interface ContentDeltaEvent {
  /** 事件类型。Event type. */
  type: 'content_delta'
  /** 增量文本内容。Delta text content. */
  text: string
}

/**
 * 推理过程增量事件
 * Reasoning delta event
 */
export interface ReasoningDeltaEvent {
  /** 事件类型。Event type. */
  type: 'reasoning_delta'
  /** 增量推理文本。Delta reasoning text. */
  text: string
}

/**
 * Token 使用量事件
 * Token usage event
 */
export interface UsageEvent {
  /** 事件类型。Event type. */
  type: 'usage'
  /** Token 使用量。Token usage. */
  usage: TokenUsage
}

/**
 * 工具开始执行事件
 * Tool start event
 */
export interface ToolStartEvent {
  /** 事件类型。Event type. */
  type: 'tool_start'
  /** 工具名称。Tool name. */
  name: string
  /** 工具参数。Tool arguments. */
  args: Record<string, any>
}

/**
 * 工具执行结束事件
 * Tool end event
 */
export interface ToolEndEvent {
  /** 事件类型。Event type. */
  type: 'tool_end'
  /** 工具名称。Tool name. */
  name: string
  /** 执行状态。Execution status. */
  status: string
  /** 执行输出。Execution output. */
  output: string
}

/**
 * 问题事件（澄清/确认）
 * Question event (clarification/confirmation)
 */
/**
 * 询问选项
 * Question option
 */
export interface QuestionOption {
  /** 机器可读取值。Machine-readable value. */
  value: string
  /** 展示文案。Display label. */
  label: string
}

export interface QuestionEvent {
  /** 事件类型。Event type. */
  type: 'question'
  /** 问题内容。Question content. */
  question: string
  /** 会话 ID。Session ID. */
  session_id: string
  /** 作答方式：text 自由文本 / choice 从选项选 / composite 选项加补充说明。
   *  选项按钮由 options 驱动，判定「是否批准」永不依赖解析自由文本。
   *  How to answer: text (free input) / choice (pick an option) / composite (option plus a
   *  note). Buttons come from options, so approval never depends on parsing free text. */
  kind: 'choice' | 'text' | 'composite'
  /** 选项列表（kind 为 choice / composite 时非空）。Options (non-empty for choice / composite). */
  options: QuestionOption[]
}

/**
 * 错误事件
 * Error event
 */
export interface ErrorEvent {
  /** 事件类型。Event type. */
  type: 'error'
  /** 错误消息。Error message. */
  message: string
}

/**
 * 完成事件
 * Done event
 */
export interface DoneEvent {
  /** 事件类型。Event type. */
  type: 'done'
}

/**
 * SSE 事件联合类型
 * SSE event union type
 */
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
