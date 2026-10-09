/**
 * 唤醒主编排 — 门面（re-export）。
 *
 * 拆分自本文件的实现已按职责迁往同目录各模块，**导入路径与导出符号保持不变**
 * （`useWakeWord.ts` 的 DI 注入与 callRouting/callAcquire/callMode 的深导入均依赖此门面）：
 * - `orchState.ts`：模块级可变状态（st 单例）、定时器、回声护栏、熔断、DI 配置
 * - `segmentFlow.ts`：段处理（handleSegment/processSegment/通话漏斗/尾随提取）
 * - `localResult.ts`：Web Speech 最终结果处理
 * - `micControl.ts`：取流/启停/开关（startListening/toggleWake/stopWake…）
 * - `watches.ts`：模块级 watch（播报门控/续聊/回聆听）
 *
 * Wake orchestrator — facade. The implementation moved to sibling modules by
 * responsibility; the import path and exported symbols are unchanged so existing
 * DI wiring and deep-import tests keep working.
 */

// R6：callMode 从本模块取 wakeEnabled（与 startListening/stopListening 同源，测试可整体替换本模块）。
// R6: callMode reads wakeEnabled from this module (same source as startListening/stopListening;
// tests can replace this module wholesale).
export { wakeEnabled } from '../store'

export { configureOrchestrator } from './orchState'
export { handleSegment } from './segmentFlow'
export { handleLocalResult } from './localResult'
export {
  stopListening,
  describeMicError,
  startListening,
  toggleWake,
  stopWake,
} from './micControl'
export { registerWatches } from './watches'
