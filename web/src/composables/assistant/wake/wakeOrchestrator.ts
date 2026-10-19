/**
 * 唤醒主编排 — 门面（re-export）。
 *
 * 拆分自本文件的实现已按职责迁往同目录各模块，导入路径与导出符号保持不变：
 * - `orchState.ts`：模块级可变状态（st 单例）、定时器、回声护栏、熔断、DI 配置
 * - `streamFlow.ts`（../stream）：流式 final → 作答/通话/指令/续聊/唤醒分流
 * - `micControl.ts`：取流/启停/开关（startListening/toggleWake/stopWake…）
 * - `watches.ts`：模块级 watch（播报门控/续聊/回聆听）
 *
 * Wake orchestrator — facade. The implementation moved to sibling modules by
 * responsibility; the import path and exported symbols are unchanged.
 */

// R6：callMode 从本模块取 wakeEnabled（与 startListening/stopListening 同源，测试可整体替换本模块）。
// R6: callMode reads wakeEnabled from this module (same source as startListening/stopListening;
// tests can replace this module wholesale).
export { wakeEnabled } from '../store'

export { configureOrchestrator } from './orchState'
export {
  stopListening,
  describeMicError,
  startListening,
  toggleWake,
  stopWake,
  ensureListening,
} from './micControl'
export { registerWatches } from './watches'
