import { computed, ref, watch } from 'vue'
import type { QuestionOption, TokenUsage, WakeWordConfig, VadConfig, CallConfig } from '../../types'
import type { Block } from '../../blocks/types'
import { makeBlock } from '../../blocks/normalize'
import { summarizeBlock } from '../../blocks/registry'

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
  /** 续聊窗口（docs/designs/03-A）：回合刚结束的免唤醒窗口 —— 窗口内的语音段直接
   *  当作新指令（不必再喊唤醒词），到期回 listening。0（followup_window_ms=0）关闭。
   *  Follow-up window (docs/designs/03-A): the wake-free window right after a turn —
   *  segments inside it are taken as fresh instructions (no wake word needed); on
   *  expiry it returns to listening. Disabled by followup_window_ms=0. */
  | 'followup'
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
 *  blocks 是事实源（思考/工具/正文/提问/汇总等模块化块），text 是派生投影
 *  （供 TTS 摘要、MiniHistory 等只读消费方过渡使用）。
 *  Chat message interface. blocks is the source of truth (modular thinking / tool /
 *  text / question / summary blocks); text is a derived projection (for TTS
 *  summaries, MiniHistory and other read-only consumers during the transition). */
export interface ChatMessage {
  /** 消息唯一标识。Unique message identifier. */
  id: string
  /** 消息角色：用户、助手或系统。Message role: user, assistant, or system. */
  role: 'user' | 'assistant' | 'system'
  /** 消息文本内容（派生投影）。Message text content (derived projection). */
  text: string
  /** 消息块列表（事实源）。Message blocks (source of truth). */
  blocks: Block[]
  /** 消息关联的工具调用（已废弃：tool 块取代，保留兼容旧读取方）。
   *  Tool calls (deprecated: superseded by tool blocks; kept for old readers). */
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
  /** 问题 ID（问答配对、陈旧作答拒收）。Question ID (pairs answers, rejects stale ones). */
  qid?: string
}

/** 编排问答：待回答的澄清/确认问题。Orchestration Q&A: pending clarification/confirmation question. */
export const pendingQuestion = ref<PendingQuestion | null>(null)
/** 助手模式：对话 = 少打断、完成不询问；任务 = 完成后询问并存档。
 *  Assistant mode: chat stays out of the way and never asks on completion; task asks and
 *  archives on completion. */
export type AssistantMode = 'chat' | 'task'

/** 模式的本地存储键。localStorage key for the mode.
 *  注：本文件持久化键统一用「xluo.」历史前缀（旧内部代号），**保留不迁移** ——
 *  换前缀会丢掉老用户已存的 history/wakeMode/assistantMode。 */
const MODE_KEY = 'xluo.assistantMode'

/**
 * 读取持久化的模式；非法值回退 chat。
 * Read the persisted mode, falling back to chat for an invalid value.
 *
 * @returns 助手模式。The assistant mode.
 */
export function loadStoredMode(): AssistantMode {
  try {
    return localStorage.getItem(MODE_KEY) === 'task' ? 'task' : 'chat'
  } catch { return 'chat' }
}

/** 当前助手模式（模块级单例，与 assistant 其余状态同模式）。
 *  Current assistant mode (module-level singleton, like the rest of the assistant state). */
export const assistantMode = ref<AssistantMode>(loadStoredMode())

/**
 * 切换助手模式并持久化。
 * Switch the assistant mode and persist it.
 *
 * @param m 目标模式。The target mode.
 */
export function setAssistantMode(m: AssistantMode) {
  assistantMode.value = m
  try { localStorage.setItem(MODE_KEY, m) } catch { /* 隐私模式忽略 / ignore in private mode */ }
}

/** 当前会话 ID。Current session ID. */
export const currentSessionId = ref('')

/** 唤醒词配置（init 时从 /api/config 用 Object.assign 原地合并，保持引用稳定）。
 *  Wake word config (merged in-place from /api/config during init using Object.assign to keep reference stable).
 *
 *  model_path 是 Vosk 时代的遗留字段（唤醒改走云端判定后前端已无人读它）：留空串只是满足生成
 *  类型的必填字段，与后端 api schema 的同名默认值（`model_path: str = ""`）一致。
 *  model_path is a leftover from the Vosk era (nothing on the frontend reads it since the wake
 *  judgement moved to the cloud): the empty string only satisfies the generated type's required
 *  field, matching the backend api schema's default (`model_path: str = ""`). */
export const wakeConfig: WakeWordConfig = { enabled: true, keywords: ['衍衡', '洛吉斯'], sensitivity: 0.5, model_path: '' }
/** VAD（语音活动检测）配置。VAD (Voice Activity Detection) configuration. */
export const vadConfig: VadConfig = { silence_threshold: 0.02, silence_duration_ms: 1500, max_duration_ms: 10000, answer_timeout_ms: 8000, min_speech_ms: 300, upload_throttle_ms: 500, barge_in: false, followup_window_ms: 6000 }
/** 通话模式配置（/api/config 的 call 段覆盖默认值）。Call-mode config (the `call` block of /api/config overrides these defaults). */
export const callConfig: CallConfig = { enabled: true, open_window_s: 8, l0_min_rms: 0.02, l0_min_seconds: 0.5, smart_turn_enabled: true, local_asr_model: '' }
/** 通话激活标志：唯一事实来源（store 级，避免 wakeOrchestrator ↔ callMode 循环导入）。Call-active flag: store-level single source of truth (avoids a wakeOrchestrator ↔ callMode import cycle). */
export const callActive = ref(false)
/** 通话开放窗口截止时刻（毫秒时间戳；0 = 不在窗口内）。Call-open-window deadline (ms timestamp; 0 = outside the window). */
export const callWindowUntil = ref(0)

/** 是否在开放窗口内（回答播报结束后 open_window_s 秒，段落 meta.in_open_window 由路由读取上报）。Whether inside the open window (open_window_s seconds after playback ends; the segment router reads this into meta.in_open_window). */
export function inOpenWindow(): boolean {
  return Date.now() < callWindowUntil.value
}

/** 回答播报结束时调用：开开放窗口。Called when playback ends: opens the window. */
export function markTurnEnded(): void {
  callWindowUntil.value = Date.now() + callConfig.open_window_s * 1000
}

/** 通话态是否应开 barge-in 监控：通话激活时强制开（spec：通话模式播报期开监控而非停麦）。 */
export function callBargeInEnabled(configFlag: boolean, active: boolean = callActive.value): boolean {
  return active || configFlag
}

/** 响应式唤醒词列表（**可多个**，命中任意一个即唤醒）。Reactive wake keywords (plural; any hit wakes). */
export const wakeKeywords = ref<string[]>([...(wakeConfig.keywords ?? [])])

/** 唤醒模式：auto = 自动优先本地、回退云端；local = 强制本地 Sherpa-ONNX；cloud = 强制云端；webspeech = 浏览器 Web Speech API。
 *  Wake mode: auto = prefer local with cloud fallback; local = force local Sherpa-ONNX; cloud = force cloud; webspeech = browser Web Speech API. */
export type WakeMode = 'auto' | 'local' | 'cloud' | 'webspeech'
const WAKE_MODE_KEY = 'xluo.wakeMode'
/** 当前唤醒模式（持久化到 localStorage）。Current wake mode (persisted to localStorage). */
export const wakeMode = ref<WakeMode>(loadWakeMode())

/** 读取持久化的唤醒模式，缺省 auto。Read the persisted wake mode, defaulting to auto. */
function loadWakeMode(): WakeMode {
  try {
    const v = localStorage.getItem(WAKE_MODE_KEY)
    return v === 'local' || v === 'cloud' || v === 'webspeech' ? v : 'auto'
  } catch { return 'auto' }
}

/** 切换唤醒模式并持久化。Switch the wake mode and persist it. */
export function setWakeMode(m: WakeMode) {
  wakeMode.value = m
  try { localStorage.setItem(WAKE_MODE_KEY, m) } catch { /* 隐私模式忽略 */ }
}

/**
 * 唤醒词的展示文案，供 UI 提示与状态文案使用，形如「衍衡」或「洛吉斯」。
 *
 * 由列表算出而非另存一个字符串：否则「界面提示的词」与「真正能唤醒的词」会有两份来源，
 * 改了配置忘改文案就会出现「按提示说却唤不醒」。
 *
 * Display text for the wake keywords, e.g. 「衍衡」或「洛吉斯」. Derived from the list rather
 * than stored separately: two sources of truth would let the on-screen hint drift from what
 * actually wakes the engine, producing "I said exactly what it told me and nothing happened".
 */
export const wakeHint = computed(() => wakeKeywords.value.map(k => `「${k}」`).join('或'))

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

/** 从本地存储加载状态。旧格式快照（消息无 blocks）直接丢弃 —— 已决定去掉旧历史。
 *  Load state from local storage. Old-format snapshots (messages without blocks)
 *  are dropped outright — old history is retired. */
function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return
    const data = JSON.parse(raw)
    if (Array.isArray(data?.messages)) {
      const withBlocks = data.messages.filter(
        (m: any) => m && Array.isArray(m.blocks),
      ) as ChatMessage[]
      if (withBlocks.length) messages.value = withBlocks.slice(-MAX_MESSAGES)
    }
    if (data?.tokenUsage && typeof data.tokenUsage === 'object') tokenUsage.value = data.tokenUsage
  } catch { /* 解析失败忽略。Parse failure: ignore. */ }
}
loadState()

/** 生成唯一消息 ID。Generate unique message ID.
 *  @returns UUID 字符串，降级为时间戳+随机数。UUID string, fallback to timestamp+random. */
export function genId() {
  try { return crypto.randomUUID() } catch { return Date.now().toString(36) + Math.random().toString(36).slice(2, 8) }
}

/** 块列表 → 纯文本投影（text 字段的单一来源）：text/code 取正文、tool 行、
 *  question 加 ❓、answer/notice 原文；thinking/summary 不进投影。
 *  Blocks → plain-text projection (single source for the text field).
 *  text/code contribute their body; tool becomes a line; question gets ❓;
 *  answer/notice contribute verbatim; thinking/summary are excluded. */
export function textProjection(blocks: Block[]): string {
  const lines: string[] = []
  for (const b of blocks) {
    const p = b.payload || {}
    switch (b.type) {
      case 'text': if (p.md) lines.push(String(p.md)); break
      case 'code': if (p.code) lines.push(String(p.code)); break
      case 'tool': lines.push(`${p.name || ''}: ${String(p.output || '').slice(0, 200)}`); break
      case 'question': if (p.question) lines.push('❓ ' + p.question); break
      case 'answer': if (p.text) lines.push(String(p.text)); break
      case 'notice': if (p.text) lines.push(String(p.text)); break
    }
  }
  return lines.join('\n')
}

/** 添加消息到消息列表。Add message to message list.
 *  @param role - 消息角色。Message role.
 *  @param text - 消息文本（自动包装为 text 块）。Message text (wrapped into a text block).
 *  @param toolCalls - 可选的工具调用（已废弃，转为 tool 块）。Optional tool calls (deprecated, converted to tool blocks). */
export function addMessage(role: ChatMessage['role'], text: string, toolCalls?: ToolCall[]) {
  const blocks: Block[] = []
  if (text) blocks.push(makeBlock('text', { md: text, variant: 'bubble' }))
  // 兼容旧调用方：toolCalls 降级为 tool 块（新代码请直接用 addBlocks）
  for (const tc of toolCalls || []) {
    blocks.push(makeBlock('tool', {
      call_id: tc.id, name: tc.name, args: tc.args || {},
      status: tc.status === 'done' ? 'ok' : tc.status === 'failed' ? 'error' : 'running',
      output: tc.result || '', output_preview: (tc.result || '').slice(0, 500),
      duration_ms: tc.durationMs,
    }))
  }
  messages.value.push({
    id: genId(),
    role,
    text: textProjection(blocks) || text,
    blocks,
    toolCalls,
    timestamp: Date.now(),
  })
  if (messages.value.length > MAX_MESSAGES) messages.value.shift()
}

/** 添加块消息（模块化入口：思考/工具/正文/提问/汇总等任意块序列）。
 *  Add a block message (modular entry: any block sequence).
 *  @param role - 消息角色。Message role.
 *  @param blocks - 块列表。Block list. */
export function addBlocks(role: ChatMessage['role'], blocks: Block[]) {
  messages.value.push({
    id: genId(),
    role,
    text: textProjection(blocks),
    blocks,
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
 *  块序列化：text 取 md、tool 取结果两行、question/answer 取问答两行；
 *  thinking/summary 不喂（防上下文膨胀）。
 *  Build multi-turn history (system injected by backend separately; tool results
 *  appended to assistant content for multi-turn reference). Block serialization:
 *  text takes md, tool its result lines, question/answer their pair; thinking and
 *  summary are not fed (keeps the context compact).
 *  @returns 包含最近 6 条消息的历史记录。History containing last 6 messages. */
export function buildHistory(): { role: string; content: string }[] {
  const history: { role: string; content: string }[] = []
  for (const m of messages.value.slice(-6)) {
    if (m.role === 'user') history.push({ role: 'user', content: m.text })
    else if (m.role === 'assistant') {
      // 有块序列化块（thinking/summary 跳过）；无块退化为 text 投影
      // Serialize blocks (thinking/summary skipped); fall back to the text projection.
      const parts: string[] = []
      for (const b of m.blocks || []) {
        const p = b.payload || {}
        if (b.type === 'text' && p.md) parts.push(String(p.md))
        else if (b.type === 'tool') parts.push(`[工具 ${p.name} 执行结果]\n${p.output || ''}`)
        else if (b.type === 'question') parts.push(`❓ ${p.question || ''}`)
        else if (b.type === 'answer') parts.push(String(p.text || ''))
        else if (b.type === 'code' && p.code) parts.push(String(p.code))
      }
      history.push({ role: 'assistant', content: parts.join('\n\n') || m.text })
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
 *  块结构随消息还原（blocks/turn_id/ts 透传；timestamp 取消息真实时间）。
 *  Switch to a session: populate conversation view with its history messages,
 *  set current session id. Block structure is restored (blocks/turn_id/ts pass
 *  through; timestamp uses the message's real time).
 *  @param sessionId - 目标会话 ID。Target session ID.
 *  @param msgs - 会话历史消息（含 blocks/ts）。Session history messages (with blocks/ts). */
export function switchSession(
  sessionId: string,
  msgs: { role: string; content: string; blocks?: Block[] | null; ts?: string | null }[],
) {
  messages.value = msgs
    .filter(m => m.role === 'user' || m.role === 'assistant')
    .map(m => {
      const blocks = m.blocks ?? (m.content ? [makeBlock('text', { md: m.content, variant: 'bubble' })] : [])
      const tsMs = m.ts ? Date.parse(m.ts) : NaN
      return {
        id: genId(),
        role: m.role as 'user' | 'assistant',
        text: m.content || textProjection(blocks),
        blocks,
        timestamp: isFinite(tsMs) ? tsMs : Date.now(),
      }
    })
  tokenUsage.value = {}
  pendingQuestion.value = null
  currentSessionId.value = sessionId
}
