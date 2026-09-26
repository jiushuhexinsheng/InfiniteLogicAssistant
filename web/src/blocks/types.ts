/**
 * 消息块协议 — 前端镜像（后端定义在 core/orchestrator/blocks.py）
 *
 * 一条消息 = 有序块列表；块是唯一事实源，text 只是派生投影。
 * 每种类型的操作/显示都是独立块：thinking / tool / text / code / image / file /
 * question / answer / notice / summary / ext:<name>（扩展块）。
 *
 * Message Block Protocol — frontend mirror (backend lives in
 * core/orchestrator/blocks.py). One message = an ordered list of blocks; blocks
 * are the single source of truth, text is only a derived projection. Every kind
 * of operation/display is its own block.
 */

/** 块的播报策略：skip 不播 / summary 播摘要 / full 全播 / auto 按类型默认。
 *  Block speech policy: skip / summary / full / auto (per-type default). */
export type TtsPolicy = 'skip' | 'summary' | 'full' | 'auto'

/** 块信封的 meta 字段。Block envelope meta fields. */
export interface BlockMeta {
  /** 播报策略。Speech policy. */
  tts?: TtsPolicy
  /** 渲染默认是否折叠。Whether collapsed by default. */
  collapsed?: boolean
  /** 是否仍在流式追加。Whether still streaming. */
  streaming?: boolean
}

/** 块信封（所有块类型公共外壳）。Block envelope (common shell for all block types). */
export interface Block {
  /** 协议版本。Protocol version. */
  v: number
  /** 块 ID。Block ID. */
  id: string
  /** 块类型（ext:<name> 为扩展块命名空间）。Block type (ext:<name> is the extension namespace). */
  type: string
  /** 产生时刻（ISO8601）。Creation time (ISO8601). */
  ts: string
  /** 所属回合（一次用户话语 → 一次编排运行 → done）。Owning turn. */
  turn_id?: string
  /** 归属（main / coordinator / sub:<type>）。Ownership. */
  agent?: string
  /** 元信息（播报策略 / 折叠 / 流式）。Meta (speech policy / collapsed / streaming). */
  meta?: BlockMeta
  /** 块载荷。Block payload. */
  payload: Record<string, any>
}

/** 内置块类型常量（ext:<name> 为扩展块）。Built-in block types (ext:<name> for extensions). */
export const BLOCK_TYPES = [
  'thinking', 'tool', 'text', 'code', 'image', 'file',
  'question', 'answer', 'notice', 'summary', 'unknown',
] as const

/** 块类型联合（字符串开放以支持 ext: 扩展块与未知类型）。
 *  Block type union (string-open for ext: extension blocks and unknown types). */
export type BlockType = (typeof BLOCK_TYPES)[number] | (string & {})

/** text 块 payload：md 为 markdown 正文，variant 区分气泡/文档排版。 */
export interface TextBlockPayload { md: string; variant?: 'bubble' | 'doc' }

/** tool 块 payload。Tool block payload. */
export interface ToolBlockPayload {
  call_id?: string
  name: string
  args?: Record<string, any>
  status?: 'running' | 'ok' | 'error' | 'cancelled' | 'denied'
  output?: string
  output_preview?: string
  truncated?: boolean
  full_len?: number
  duration_ms?: number
}

/** question 块 payload（自由文本为主，options 为语音匹配扩展点）。
 *  Question block payload (free text first; options is the voice-matching extension point). */
export interface QuestionBlockPayload {
  qid?: string
  question: string
  kind?: 'text' | 'choice' | 'composite'
  options?: { value: string; label: string; aliases?: string[] }[]
  status?: 'pending' | 'answered'
  answer_block_id?: string
}

/** answer 块 payload。Answer block payload. */
export interface AnswerBlockPayload {
  qid?: string
  text: string
  choice?: string | null
  source?: 'typed' | 'voice' | 'button' | string
}

/** notice 块 payload。Notice block payload. */
export interface NoticeBlockPayload { level?: 'info' | 'warn' | 'error'; text: string }

/** summary 块 payload（回合汇总卡：聚合回看 + 语音播报统一出口）。
 *  Summary block payload (turn summary card: aggregated review + unified speech exit). */
export interface SummaryBlockPayload {
  status?: string
  summary_text?: string
  tts_text?: string
  counts?: Record<string, number>
  block_ids?: string[]
}

/** 渲染皮肤：full 完整 / summary 摘要 / task 任务日志。Render skin: full / summary / task. */
export type Skin = 'full' | 'summary' | 'task'
