import { computed } from 'vue'
import { STATE_VISUALS, resolveStateLabel, type StateVisual } from './useAssistantVisuals'
import type { WakeWordConfig, VadConfig } from '../types'
import {
  state, messages, expanded, wakeEnabled, wakeKeyword, partialText, statusLine, tokenUsage,
  wakeConfig, vadConfig, clearMessages, pendingQuestion, currentSessionId,
  modelLoading, modelProgress,
} from './assistant/store'
import { sendText, retryTool, cancelTool, abortChat, sendAnswer } from './assistant/useChat'
import { toggleWake, stopWake } from './assistant/useWakeWord'

/** 类型沿用原模块路径导出，避免改动各组件 import。Types are re-exported from the original module path to avoid changing component imports. */
export type { AsstState, ToolCall, ChatMessage } from './assistant/store'

/** 模块级初始化标志，确保只初始化一次。Module-level initialization flag to ensure only one initialization. */
let initialized = false

/** config.yaml 的 model_path 可能是目录名（如 "models/vosk-model-small-cn-0.22"），
 *  而 vosk.createModel 需要指向可下载的 .tar.gz 文件 URL。归一化为服务端相对 URL。
 *  The model_path in config.yaml may be a directory name (e.g., "models/vosk-model-small-cn-0.22"),
 *  but vosk.createModel requires a downloadable .tar.gz file URL. Normalize to a server-relative URL. */
function resolveModelPath(p?: string): string {
  const def = '/models/vosk-model-small-cn-0.22.tar.gz'
  if (!p) return def
  let path = p.trim()
  if (!path.startsWith('/')) path = '/' + path
  if (!/\.tar\.gz$/i.test(path)) path = path + '.tar.gz'
  return path
}

/** 初始化（幂等：根组件只调用一次，防路由重挂/热更新重复预热）。
 *  Initialization (idempotent: only called once by root component, prevents duplicate warm-up from route remount/hot update).
 *  @param config - 可选的唤醒词和 VAD 配置。Optional wake word and VAD configuration. */
function init(config?: { wake?: Partial<WakeWordConfig>; vad?: Partial<VadConfig> }) {
  if (initialized) return
  initialized = true
  if (config?.wake) {
    Object.assign(wakeConfig, config.wake)
    wakeConfig.model_path = resolveModelPath(config.wake.model_path)
    wakeKeyword.value = wakeConfig.keyword || wakeKeyword.value
  }
  if (config?.vad) Object.assign(vadConfig, config.vad)
  state.value = 'idle'
  if (typeof WakeWordEngine === 'undefined') {
    console.warn('[Asst] WakeWordEngine not loaded, wake disabled')
  }
  // 不预热模型：vosk 中文模型约 40MB，留到首次开启唤醒（toggleWake）时才下载，避免首屏流量浪费
  // Do not pre-warm model: vosk Chinese model is about 40MB, delay download until first wake toggle to avoid initial page load traffic waste.
}

/** 销毁助手实例，中止聊天和唤醒监听。Destroy assistant instance, abort chat and wake listening. */
function destroy() {
  abortChat()
  stopWake()
}

/** 状态视觉（数据驱动，来自 useAssistantVisuals）。State visuals (data-driven, from useAssistantVisuals). */
const visual = computed<StateVisual>(() => STATE_VISUALS[state.value] || STATE_VISUALS.idle)
const stateLabel = computed(() => resolveStateLabel(visual.value, wakeKeyword.value))
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
    wakeKeyword,
    partialText,
    statusLine,
    tokenUsage,
    // 唤醒模型下载 / Wake model download
    modelLoading,
    modelProgress,
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
