/**
 * 语音链路 — 瘦包装层。
 *
 * 对外导出 `toggleWake` / `stopWake` / `describeMicError`；内部委托给
 * `wake/wakeOrchestrator`（麦克风流 + 流式会话 + 模块级 watch）。
 *
 * **依赖注入点**：本模块把 `api` / `sendText` / `sendAnswer` / `speaking` /
 * `stopSpeak` / `enterCall` 注入编排器 —— 测试只需 mock 本模块的导入路径即可。
 *
 * Voice pipeline — thin wrapper layer. It exports toggleWake / stopWake /
 * describeMicError and delegates to `wake/wakeOrchestrator` (mic stream + streaming
 * session + module-level watches).
 *
 * **Dependency injection point**: this module injects api / sendText / sendAnswer /
 * speaking / stopSpeak / enterCall into the orchestrator — tests only need to mock this
 * module's import paths.
 */

import { api } from '../../api'
import { speaking, stopSpeak } from './useTts'
import { sendText, sendAnswer } from './useChat'
import { enterCallFromWake } from './callMode'
import {
  configureOrchestrator,
  describeMicError as _describeMicError,
  toggleWake as _toggleWake,
  stopWake as _stopWake,
  registerWatches,
} from './wake/wakeOrchestrator'

// 注入依赖：编排器通过这些引用来调用 API 和聊天方法
// Inject dependencies: the orchestrator uses these references for API and chat calls
// enterCall：静待中裸唤醒 → 通话聆听（callMode，DI 注入避免 wake 族反向 import callMode）。
// enterCall: bare wake in standby → call listening (callMode, injected via DI so the wake
// family never imports callMode directly).
configureOrchestrator({ api, sendText, sendAnswer, speaking, stopSpeak, enterCall: enterCallFromWake })

// 注册模块级 watch（幂等，首次 import 时执行一次）
// Register module-level watches (idempotent, runs once on first import)
registerWatches()

/** 麦克风错误 → 用户可理解的中文提示。Microphone error → user-friendly Chinese message. */
export const describeMicError = _describeMicError

/** 开启/关闭唤醒。Toggle wake word detection on/off. */
export const toggleWake = _toggleWake

/** 页面销毁时收尾。Cleanup on page destruction. */
export const stopWake = _stopWake