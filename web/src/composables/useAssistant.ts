import { computed } from 'vue'
import { STATE_VISUALS, resolveStateLabel, type StateVisual } from './useAssistantVisuals'
import type { WakeWordConfig, VadConfig, CallConfig } from '../types'
import {
  state, messages, expanded, wakeEnabled, wakeKeywords, wakeHint, partialText, statusLine, tokenUsage,
  wakeConfig, vadConfig, callConfig, hardwareConfig, streamingEnabled,
  clearMessages, pendingQuestion, currentSessionId,
} from './assistant/store'
import { DEFAULT_WAKE_KEYWORDS, resetRuntimeConfig } from './assistant/storeConfig'
import type { HardwareConfig } from './assistant/store'
import { sendText, retryTool, cancelTool, abortChat, sendAnswer, forkAt, sendEdited, regenerate, outboxCount, clearQueued } from './assistant/useChat'
import { toggleWake, stopWake } from './assistant/useWakeWord'
import { toggleCall } from './assistant/callMode'

/** 类型沿用原模块路径导出，避免改动各组件 import。Types are re-exported from the original module path to avoid changing component imports. */
export type { AsstState, ChatMessage } from './assistant/store'

/** 模块级初始化标志，确保只初始化一次。Module-level initialization flag to ensure only one initialization. */
let initialized = false

/** /api/config 中驱动前端运行时行为的子集。The /api/config subset that drives frontend runtime behavior. */
export interface ServerRuntimeConfig {
  wake?: Partial<WakeWordConfig>
  vad?: Partial<VadConfig>
  call?: Partial<CallConfig>
  hardware?: Partial<HardwareConfig>
  streaming?: boolean
}

/**
 * 把服务端配置应用到运行时单例。
 *
 * 设置页保存后 `refreshConfig()` 只换 `app.config`，旧实现不会重新写入这些模块级单例，
 * 于是「改了唤醒词/续聊窗/idle 超时/输入设备后必须刷新页面」才生效。这里抽出统一入口，
 * App.vue 深度 watch `app.config` 即可热同步。
 *
 * **先重置默认再合并**：配置里被删掉的键必须回到默认值；否则 Object.assign 只覆盖
 * 出现过的键，删掉的键会永远停在上一轮下发值上。
 *
 * Apply server config to the runtime singletons. After a settings save, `refreshConfig()`
 * only swapped `app.config`; the module-level singletons kept their old values, so wake
 * keywords / followup window / idle timeout / input device only took effect after a reload.
 * App.vue deep-watches `app.config` and calls this. **Reset before merge**: keys removed
 * from the config must fall back to defaults, since Object.assign never deletes.
 * @param config - /api/config 的运行时子集。Runtime subset of /api/config.
 */
export function applyServerConfig(config?: ServerRuntimeConfig) {
  resetRuntimeConfig()
  if (config?.wake) Object.assign(wakeConfig, config.wake)
  // 以 /api/config 下发的唤醒词为准；缺省（空数组）时保留内置默认，避免界面提示为空
  // Take the keywords from /api/config; keep the built-in default when the list is empty,
  // so the on-screen hint never renders blank.
  wakeKeywords.value = [
    ...(wakeConfig.keywords?.length ? wakeConfig.keywords : DEFAULT_WAKE_KEYWORDS),
  ]
  if (config?.vad) Object.assign(vadConfig, config.vad)
  if (config?.call) Object.assign(callConfig, config.call)
  if (config?.hardware) Object.assign(hardwareConfig, config.hardware)
  if (typeof config?.streaming === 'boolean') streamingEnabled.value = config.streaming
}

/** 初始化（幂等：根组件只调用一次，防路由重挂/热更新重复预热）。
 *  Initialization (idempotent: only called once by root component, prevents duplicate warm-up from route remount/hot update).
 *  @param config - 可选的唤醒词和 VAD 配置。Optional wake word and VAD configuration. */
function init(config?: ServerRuntimeConfig) {
  if (initialized) return
  initialized = true
  applyServerConfig(config)
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

/**
 * 清空对话：**先**中止当前回合（带着旧 sessionId 调 stopTask 停掉后端任务），
 * 再清本地消息与会话 id。顺序不可换 —— abortChat 读 currentSessionId，先清就没人可停。
 * Clear the conversation: **first** abort the running turn (stopTask with the old
 * sessionId), then clear local messages and the session id. The order matters: abortChat
 * reads currentSessionId, so clearing first leaves nothing to stop.
 */
function clearConversation() {
  abortChat()
  clearMessages()
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
    // 运行时配置（设置保存后热同步）/ Runtime config (hot-synced after a settings save)
    streamingEnabled,
    applyServerConfig,
    // 方法 / Methods
    init,
    destroy,
    toggleWake,
    // 双击悬浮球入口：通话开关（唤醒仍走徽章 toggleWake，R7）。
    // Double-click float-ball entry: call toggle (wake stays on the badge's toggleWake, R7).
    toggleCall,
    clearMessages: clearConversation,
    sendText,
    sendAnswer,
    retryTool,
    cancelTool,
    // 分叉 / 编辑重发 / 重新生成 / 排队（docs/designs/06、07）
    forkAt,
    sendEdited,
    regenerate,
    outboxCount,
    clearQueued,
  }
}
