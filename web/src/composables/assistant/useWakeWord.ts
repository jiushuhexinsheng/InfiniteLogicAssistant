/**
 * 唤醒链路 — 瘦包装层。
 *
 * 保持对外 API 不变（`toggleWake` / `stopWake` / `handleSegment` / `handleLocalResult` / `describeMicError`），
 * 内部全部委托给模块化的 `wake/wakeOrchestrator`。
 *
 * **依赖注入点**：本模块是 `api` / `sendText` / `sendAnswer` / `speaking` 的唯一导入者，
 * 通过 `configureOrchestrator()` 注入到编排器 —— 测试只需 mock 本模块的导入路径即可。
 *
 * Wake pipeline — thin wrapper layer.
 * Preserves the public API surface; all logic is delegated to `wake/wakeOrchestrator`.
 *
 * **Dependency injection point**: this module is the sole importer of `api` / `sendText` /
 * `sendAnswer` / `speaking`, injected into the orchestrator via `configureOrchestrator()` —
 * tests only need to mock this module's import paths.
 */

import { api } from '../../api'
import { speaking, stopSpeak } from './useTts'
import { sendText, sendAnswer } from './useChat'
import {
  configureOrchestrator,
  handleSegment as _handleSegment,
  handleLocalResult as _handleLocalResult,
  describeMicError as _describeMicError,
  toggleWake as _toggleWake,
  stopWake as _stopWake,
  registerWatches,
} from './wake/wakeOrchestrator'

// 注入依赖：编排器通过这些引用来调用 API 和聊天方法
// Inject dependencies: the orchestrator uses these references for API and chat calls
configureOrchestrator({ api, sendText, sendAnswer, speaking, stopSpeak })

// 注册模块级 watch（幂等，首次 import 时执行一次）
// Register module-level watches (idempotent, runs once on first import)
registerWatches()

/** 处理一段音频（云端链路）。导出供测试。Handle one audio segment (cloud path). Exported for tests. */
export const handleSegment = _handleSegment

/** 处理本地识别结果（Web Speech API 路径）。导出供测试。Handle a local recognition result. Exported for tests. */
export const handleLocalResult = _handleLocalResult

/** 麦克风错误 → 用户可理解的中文提示。Microphone error → user-friendly Chinese message. */
export const describeMicError = _describeMicError

/** 开启/关闭唤醒。Toggle wake word detection on/off. */
export const toggleWake = _toggleWake

/** 页面销毁时收尾。Cleanup on page destruction. */
export const stopWake = _stopWake