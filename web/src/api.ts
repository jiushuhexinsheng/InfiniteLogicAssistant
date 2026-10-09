/**
 * API 模块 - 封装与后端的所有 HTTP 通信
 * API Module - Encapsulates all HTTP communication with the backend
 *
 * 本体为导出门面：HTTP 封装 / 端点集合 / 编排 SSE 拆出为 ./api/ 子模块，
 * 原导入路径与导出面不变（`import { api, streamUtter } from './api'` 照旧）。
 * This file is the export facade: the HTTP wrappers / endpoint collection /
 * orchestration SSE live in ./api/ submodules; the original import path and
 * export surface are unchanged (`import { api, streamUtter } from './api'` still works).
 */
import type { components } from './api/generated'

export { api } from './api/endpoints'
export { streamUtter } from './api/sse'
export type { UtterHandlers } from './api/sse'

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
