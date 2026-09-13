import { ref, watch } from 'vue'
import type { QuestionOption, TokenUsage, WakeWordConfig, VadConfig } from '../../types'

/** 助手状态类型，定义状态机的所有可能状态。
 *  Assistant state type, defines all possible states of the state machine. */
export type AsstState =
  | 'idle'
  | 'listening'
  /** 等待操作者回答某个提问：转写将走答案通道，而不是开新一轮。
   *  Waiting for the operator to answer a question: the transcript goes to the answer
   *  channel rather than starting a new turn. */
  | 'awaiting_answer'
  /** 等待回答超时后的待机：引擎仍在听唤醒词，唤醒后回到**本题**续答。
   *  Standby after the answer timeout: the engine still listens for the wake word, and
   *  waking resumes *this* question. */
  | 'standby'
  | 'recording'
  | 'transcribing'
  | 'thinking'
  | 'tool_calling'
  | 'responding'
  | 'done'
  | 'error'

/** 工具调用接口，记录工具执行的详细信息。
 *  Tool call interface, records detailed information of tool execution. */
export interface ToolCall {
  /** 工具调用唯一标识。Unique identifier for tool call. */
  id: string
  /** 工具名称。Tool name. */
  name: string
  /** 工具调用参数。Tool call arguments. */
  args: Record<string, any>
  /** 工具执行结果。Tool execution result. */
  result?: string
  /** 工具调用状态。Tool call status. */
  status: 'pending' | 'running' | 'done' | 'failed'
  /** 工具执行耗时（毫秒）。Tool execution duration (milliseconds). */
  durationMs?: number
}

/** 聊天消息接口，表示对话中的一条消息。
 *  Chat message interface, represents a message in the conversation. */
export interface ChatMessage {
  /** 消息唯一标识。Unique message identifier. */
  id: string
  /** 消息角色：用户、助手或系统。Message role: user, assistant, or system. */
  role: 'user' | 'assistant' | 'system'
  /** 消息文本内容。Message text content. */
  text: string
  /** 消息关联的工具调用。Tool calls associated with the message. */
  toolCalls?: ToolCall[]
  /** 消息时间戳。Message timestamp. */
  timestamp: number
}

/** 会话内消息上限（控制台需保留完整记录；buildHistory 只取最近 6 条，与 LLM 上下文解耦）。
 *  Maximum messages per session (console needs complete records; buildHistory only takes last 6, decoupled from LLM context). */
export const MAX_MESSAGES = 200

/** 模块级单例状态 —— 全站唯一数据源（悬浮球 / 开始页 / 控制台共享）。
 *  useAssistant() 只是返回这份单例的引用。
 *  Module-level singleton state —— site-wide single data source (shared by floating ball / start page / console).
 *  useAssistant() just returns a reference to this singleton. */

/** 助手当前状态。Assistant current state. */
export const state = ref<AsstState>('idle')
/** 聊天消息列表。Chat message list. */
export const messages = ref<ChatMessage[]>([])
/** 控制台面板是否展开。Whether console panel is expanded. */
export const expanded = ref(false)
/** 唤醒词功能是否启用。Whether wake word feature is enabled. */
export const wakeEnabled = ref(false)
/** 模型是否正在加载。Whether model is loading. */
export const modelLoading = ref(false)
/** 模型加载进度（0-100）。Model loading progress (0-100). */
export const modelProgress = ref(0)
/** 部分识别文本（流式输出）。Partial recognition text (streaming output). */
export const partialText = ref('')
/** 状态行文本。Status line text. */
export const statusLine = ref('')
/** Token 使用量统计。Token usage statistics. */
export const tokenUsage = ref<TokenUsage>({})

/** 待回答的提问（含作答方式与选项，决定前端渲染按钮还是输入框）。
 *  Pending question (with how to answer and its options, deciding whether the frontend
 *  renders buttons or an input). */
export interface PendingQuestion {
  /** 问题内容。Question content. */
  text: string
  /** 作答方式。How to answer. */
  kind: 'choice' | 'text' | 'composite'
  /** 选项列表（choice / composite 用）。Options (for choice / composite). */
  options: QuestionOption[]
}

/** 编排问答：待回答的澄清/确认问题。Orchestration Q&A: pending clarification/confirmation question. */
export const pendingQuestion = ref<PendingQuestion | null>(null)
/** 当前会话 ID。Current session ID. */
export const currentSessionId = ref('')

/** 唤醒词配置（init 时从 /api/config 用 Object.assign 原地合并，保持引用稳定）。
 *  Wake word config (merged in-place from /api/config during init using Object.assign to keep reference stable). */
export const wakeConfig: WakeWordConfig = { enabled: true, keyword: '小逻小逻', sensitivity: 0.5, model_path: '/models/vosk-model-small-cn-0.22.tar.gz' }
/** VAD（语音活动检测）配置。VAD (Voice Activity Detection) configuration. */
export const vadConfig: VadConfig = { silence_threshold: 0.02, silence_duration_ms: 1500, max_duration_ms: 10000 }
/** 响应式唤醒关键字，供 UI 提示与状态文案使用。Reactive wake keyword for UI hints and status text. */
export const wakeKeyword = ref(wakeConfig.keyword)

/** 消息与 token 用量持久化的本地存储键。Local storage key for message and token usage persistence. */
const STORAGE_KEY = 'xluo.history'

/** 保存状态到本地存储。Save state to local storage. */
function saveState() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      messages: messages.value.slice(-MAX_MESSAGES),
      tokenUsage: tokenUsage.value,
    }))
  } catch { /* 隐私模式/配额满：忽略。Privacy mode/quota full: ignore. */ }
}

let saveTimer: ReturnType<typeof setTimeout> | null = null
watch([messages, tokenUsage], () => {
  // 流式期间高频变化，合并到 ~500ms 落盘一次。
  // During streaming, high-frequency changes are batched to ~500ms intervals for persistence.
  if (saveTimer) return
  saveTimer = setTimeout(() => { saveTimer = null; saveState() }, 500)
}, { deep: true })

/** 从本地存储加载状态。Load state from local storage. */
function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return
    const data = JSON.parse(raw)
    if (Array.isArray(data?.messages)) messages.value = data.messages.slice(-MAX_MESSAGES)
    if (data?.tokenUsage && typeof data.tokenUsage === 'object') tokenUsage.value = data.tokenUsage
  } catch { /* 解析失败忽略。Parse failure: ignore. */ }
}
loadState()

/** 生成唯一消息 ID。Generate unique message ID.
 *  @returns UUID 字符串，降级为时间戳+随机数。UUID string, fallback to timestamp+random. */
export function genId() {
  try { return crypto.randomUUID() } catch { return Date.now().toString(36) + Math.random().toString(36).slice(2, 8) }
}

/** 添加消息到消息列表。Add message to message list.
 *  @param role - 消息角色。Message role.
 *  @param text - 消息文本。Message text.
 *  @param toolCalls - 可选的工具调用。Optional tool calls. */
export function addMessage(role: ChatMessage['role'], text: string, toolCalls?: ToolCall[]) {
  messages.value.push({
    id: genId(),
    role,
    text,
    toolCalls,
    timestamp: Date.now(),
  })
  if (messages.value.length > MAX_MESSAGES) messages.value.shift()
}

/** 清空所有消息和 token 使用量。Clear all messages and token usage. */
export function clearMessages() {
  messages.value = []
  tokenUsage.value = {}
}

/** 唤醒失败统一处理：错误状态 + 状态行 + 消息区醒目提示 + 自动展开面板。
 *  Unified wake failure handling: error state + status line + prominent message area hint + auto-expand panel.
 *  @param msg - 错误消息。Error message. */
export function failWake(msg: string) {
  state.value = 'error'
  statusLine.value = msg
  addMessage('system', '⚠️ ' + msg)
  expanded.value = true // 自动展开面板，确保用户看到错误信息。Auto-expand panel to ensure user sees error message.
}

/** 多轮历史构建（system 由后端各自注入；工具结果拼入 assistant content，供多轮引用）。
 *  Build multi-turn history (system injected by backend separately; tool results appended to assistant content for multi-turn reference).
 *  @returns 包含最近 6 条消息的历史记录。History containing last 6 messages. */
export function buildHistory(): { role: string; content: string }[] {
  const history: { role: string; content: string }[] = []
  for (const m of messages.value.slice(-6)) {
    if (m.role === 'user') history.push({ role: 'user', content: m.text })
    else if (m.role === 'assistant') {
      let content = m.text
      // 附加工具执行结果，供后续指令引用。
      // Append tool execution results for subsequent command reference.
      if (m.toolCalls?.length) {
        const results = m.toolCalls
          .map((tc) => `[工具 ${tc.name} 执行结果]\n${tc.result || ''}`)
          .join('\n\n')
        content = `${content}\n\n${results}`
      }
      history.push({ role: 'assistant', content })
    }
  }
  return history
}

/** 会话管理（控制台会话视图用）：新建 / 切换会话。
 *  Session management (for console session view): create / switch session.
 *  @param sessionId - 会话 ID，默认为空字符串。Session ID, defaults to empty string. */
export function createNewSession(sessionId = '') {
  messages.value = []
  tokenUsage.value = {}
  partialText.value = ''
  currentSessionId.value = sessionId
}

/** 切换到某会话：用其历史消息填充对话视图，设置当前会话 id。
 *  Switch to a session: populate conversation view with its history messages, set current session id.
 *  @param sessionId - 目标会话 ID。Target session ID.
 *  @param msgs - 会话历史消息。Session history messages. */
export function switchSession(sessionId: string, msgs: { role: string; content: string }[]) {
  messages.value = msgs
    .filter(m => m.role === 'user' || m.role === 'assistant')
    .map(m => ({ id: genId(), role: m.role as 'user' | 'assistant', text: m.content, timestamp: Date.now() }))
  tokenUsage.value = {}
  pendingQuestion.value = null
  currentSessionId.value = sessionId
}
