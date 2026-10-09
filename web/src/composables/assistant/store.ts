import { ref, watch } from 'vue'
import type { QuestionOption, TokenUsage } from '../../types'
import type { Block } from '../../blocks/types'
import { summarizeBlock } from '../../blocks/registry'
import { saveState, loadState } from './storePersist'

// ─── 导出门面：配置簇 / 消息操作拆出为同目录子模块，原导入路径与导出面不变（纯移动）。
// Facade: the config cluster / message operations live in sibling submodules; the
// original import path and export surface are unchanged (pure move).
export {
  wakeConfig, vadConfig, callConfig, callActive, callWindowUntil, inOpenWindow, markTurnEnded,
  callBargeInEnabled, wakeKeywords, wakeMode, setWakeMode, wakeHint,
} from './storeConfig'
export type { WakeMode } from './storeConfig'
export {
  genId, textProjection, addMessage, addBlocks, clearMessages, failWake,
  buildHistory, createNewSession, switchSession,
} from './storeMessages'

/** 助手状态类型，定义状态机的所有可能状态。
 *  Assistant state type, defines all possible states of the state machine. */
export type AsstState =
  | 'idle'
  | 'listening'
  /** 等待操作者回答某个提问：转写将走答案通道，而不是开新一轮。
   *  Waiting for the operator to answer a question: the transcript goes to the answer
   *  channel rather than starting a new turn. */
  | 'awaiting_answer'
  // standby（回答超时后的待机）已随「取消限时回答」删除：回答永不限时，不再有超时态。
  // standby (the post-answer-timeout idle) is gone with the unlimited answer window:
  // answers are never timed out, so there is no timeout state to fall into.
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

// 持久化落盘（saveState/loadState 在 ./storePersist）：watch 注册与初始加载
// 保持「模块加载即执行」的原时机 —— 先注册 watch 再 loadState（与拆分前一致）。
// Persistence (saveState/loadState live in ./storePersist): the watch registration
// and initial load keep their original module-load timing — watch first, then
// loadState (same order as before the split).
let saveTimer: ReturnType<typeof setTimeout> | null = null
watch([messages, tokenUsage], () => {
  // 流式期间高频变化，合并到 ~500ms 落盘一次。
  // During streaming, high-frequency changes are batched to ~500ms intervals for persistence.
  if (saveTimer) return
  saveTimer = setTimeout(() => { saveTimer = null; saveState() }, 500)
}, { deep: true })
loadState()
