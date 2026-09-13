import { computed } from 'vue'
import { STATE_VISUALS, resolveStateLabel, type StateVisual } from './useAssistantVisuals'
import type { WakeWordConfig, VadConfig } from '../types'
import {
  state, messages, expanded, wakeEnabled, wakeKeywords, wakeHint, partialText, statusLine, tokenUsage,
  wakeConfig, vadConfig, clearMessages, pendingQuestion, currentSessionId,
} from './assistant/store'
import { sendText, retryTool, cancelTool, abortChat, sendAnswer } from './assistant/useChat'
import { toggleWake, stopWake } from './assistant/useWakeWord'

/** 类型沿用原模块路径导出，避免改动各组件 import。Types are re-exported from the original module path to avoid changing component imports. */
export type { AsstState, ToolCall, ChatMessage } from './assistant/store'

/** 模块级初始化标志，确保只初始化一次。Module-level initialization flag to ensure only one initialization. */
let initialized = false

/** 初始化（幂等：根组件只调用一次，防路由重挂/热更新重复预热）。
 *  Initialization (idempotent: only called once by root component, prevents duplicate warm-up from route remount/hot update).
 *  @param config - 可选的唤醒词和 VAD 配置。Optional wake word and VAD configuration. */
function init(config?: { wake?: Partial<WakeWordConfig>; vad?: Partial<VadConfig> }) {
  if (initialized) return
  initialized = true
  if (config?.wake) {
    Object.assign(wakeConfig, config.wake)
    // 以 /api/config 下发的唤醒词为准；缺省（空数组）时保留内置默认，避免界面提示为空
    // Take the keywords from /api/config; keep the built-in default when the list is empty,
    // so the on-screen hint never renders blank.
    if (wakeConfig.keywords?.length) wakeKeywords.value = [...wakeConfig.keywords]
  }
  if (config?.vad) Object.assign(vadConfig, config.vad)
  state.value = 'idle'
  // 唤醒链路已改走云端判定（VAD 分段 → POST /api/voice/wake），前端不再加载本地模型，
  // 因此既没有引擎探测也没有模型预热。
  // The wake pipeline now judges in the cloud (VAD segments → POST /api/voice/wake), so the
  // frontend loads no local model: no engine probe, no model warm-up.
}

/** 销毁助手实例，中止聊天和唤醒监听。Destroy assistant instance, abort chat and wake listening. */
function destroy() {
  abortChat()
  stopWake()
}

/** 状态视觉（数据驱动，来自 useAssistantVisuals）。State visuals (data-driven, from useAssistantVisuals). */
const visual = computed<StateVisual>(() => STATE_VISUALS[state.value] || STATE_VISUALS.idle)
const stateLabel = computed(() => resolveStateLabel(visual.value, wakeHint.value))
const stateColor = computed(() => visual.value.color)

/** 对外：返回单例引用（全站共享同一份状态）。External: returns singleton reference (site-wide shared state).
 *  @returns 包含状态、视觉、方法等的助手接口。Assistant interface containing state, visuals, methods, etc. */
export function useAssistant() {
  return {
    // 状态 / State
    state,
    visual,
    stateLabel,
    stateColor,
    messages,
    expanded,
    wakeEnabled,
    wakeKeywords, wakeHint,
    partialText,
    statusLine,
    tokenUsage,
    // 编排问答 / Orchestrate Q&A
    pendingQuestion,
    currentSessionId,
    // 方法 / Methods
    init,
    destroy,
    toggleWake,
    clearMessages,
    sendText,
    sendAnswer,
    retryTool,
    cancelTool,
  }
}
