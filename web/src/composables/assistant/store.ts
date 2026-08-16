import { ref } from 'vue'
import type { TokenUsage, WakeWordConfig, VadConfig } from '../../types'

// ─── 状态机 ───
export type AsstState =
  | 'idle'
  | 'listening'
  | 'recording'
  | 'transcribing'
  | 'thinking'
  | 'tool_calling'
  | 'responding'
  | 'done'
  | 'error'

export interface ToolCall {
  id: string
  name: string
  args: Record<string, any>
  result?: string
  status: 'pending' | 'running' | 'done' | 'failed'
  durationMs?: number
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  text: string
  toolCalls?: ToolCall[]
  timestamp: number
}

// 会话内消息上限（控制台需保留完整记录；buildHistory 只取最近 6 条，与 LLM 上下文解耦）
export const MAX_MESSAGES = 200

// ════════════════════════════════════════════════════════════════
// 模块级单例状态 —— 全站唯一数据源（悬浮球 / 开始页 / 控制台共享）。
// useAssistant() 只是返回这份单例的引用。
// ════════════════════════════════════════════════════════════════

// ── 状态 ──
export const state = ref<AsstState>('idle')
export const messages = ref<ChatMessage[]>([])
export const expanded = ref(false)
export const wakeEnabled = ref(false)
export const partialText = ref('')
export const statusLine = ref('')
export const tokenUsage = ref<TokenUsage>({})

// 编排问答：待回答的澄清/确认问题 与 当前会话 id
export const pendingQuestion = ref('')
export const currentSessionId = ref('')

// 唤醒词配置（init 时从 /api/config 用 Object.assign 原地合并，保持引用稳定）
export const wakeConfig: WakeWordConfig = { enabled: true, keyword: '小逻小逻', sensitivity: 0.5, model_path: '/models/vosk-model-small-cn-0.22.tar.gz' }
export const vadConfig: VadConfig = { silence_threshold: 0.02, silence_duration_ms: 1500, max_duration_ms: 10000 }
export const wakeKeyword = ref(wakeConfig.keyword)  // 响应式 keyword，供 UI 提示与状态文案

// ── 消息管理 ──
export function genId() {
  try { return crypto.randomUUID() } catch { return Date.now().toString(36) + Math.random().toString(36).slice(2, 8) }
}

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

// ── 清空消息 ──
export function clearMessages() {
  messages.value = []
  tokenUsage.value = {}
}

// ── 唤醒失败统一处理：错误状态 + 状态行 + 消息区醒目提示 + 自动展开面板 ──
export function failWake(msg: string) {
  state.value = 'error'
  statusLine.value = msg
  addMessage('system', '⚠️ ' + msg)
  expanded.value = true // 自动展开面板，确保用户看到错误信息
}

// ── 多轮历史构建（system 由后端各自注入；工具结果拼入 assistant content，供多轮引用）──
export function buildHistory(): { role: string; content: string }[] {
  const history: { role: string; content: string }[] = []
  for (const m of messages.value.slice(-6)) {
    if (m.role === 'user') history.push({ role: 'user', content: m.text })
    else if (m.role === 'assistant') {
      let content = m.text
      // 附加工具执行结果，供后续指令引用
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
