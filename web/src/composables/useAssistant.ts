import { computed } from 'vue'
import { STATE_VISUALS, resolveStateLabel, type StateVisual } from './useAssistantVisuals'
import type { WakeWordConfig, VadConfig } from '../types'
import {
  state, messages, expanded, wakeEnabled, wakeKeyword, partialText, statusLine, tokenUsage,
  wakeConfig, vadConfig, clearMessages, pendingQuestion, currentSessionId,
} from './assistant/store'
import { sendText, retryTool, cancelTool, abortChat, sendAnswer } from './assistant/useChat'
import { toggleWake, stopWake } from './assistant/useWakeWord'

// 类型沿用原模块路径导出，避免改动各组件 import
export type { AsstState, ToolCall, ChatMessage } from './assistant/store'

let initialized = false

/** config.yaml 的 model_path 可能是目录名（如 "models/vosk-model-small-cn-0.22"），
 *  而 vosk.createModel 需要指向可下载的 .tar.gz 文件 URL。归一化为服务端相对 URL。 */
function resolveModelPath(p?: string): string {
  const def = '/models/vosk-model-small-cn-0.22.tar.gz'
  if (!p) return def
  let path = p.trim()
  if (!path.startsWith('/')) path = '/' + path
  if (!/\.tar\.gz$/i.test(path)) path = path + '.tar.gz'
  return path
}

// ── 初始化（幂等：根组件只调用一次，防路由重挂/热更新重复预热）──
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
}

function destroy() {
  abortChat()
  stopWake()
}

// ── 状态视觉（数据驱动，来自 useAssistantVisuals）──
const visual = computed<StateVisual>(() => STATE_VISUALS[state.value] || STATE_VISUALS.idle)
const stateLabel = computed(() => resolveStateLabel(visual.value, wakeKeyword.value))
const stateColor = computed(() => visual.value.color)

// ─── 对外：返回单例引用（全站共享同一份状态）───
export function useAssistant() {
  return {
    // 状态
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
    // 编排问答
    pendingQuestion,
    currentSessionId,
    // 方法
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
