// 唤醒编排的公共入口（原 orchState.ts 拆分后的聚合层）。
//
// 拆分原则：状态与依赖注入在 orchStore，上传闸门/回声护栏在 gate，三族计时器在
// timers，上传熔断在 breaker，识别中状态在 transcribe，静待进通话/弃题在 callEntry。
// 本文件只做 re-export，**保持既有导入路径与成员形状不变** —— 消费方
// （streamFlow / micControl / watches / useChat / tests）零改动。
//
// Public entry for wake orchestration (the aggregation layer after splitting
// orchState.ts): state and DI live in orchStore, the upload gate / echo guard in gate,
// the three timer families in timers, the upload breaker in breaker, the transcribing
// state in transcribe, and call entry / abandonment in callEntry. This file only
// re-exports, keeping import paths and the public shape stable so consumers need no
// changes.

export { st, configureOrchestrator } from './orchStore'
export type { OrchestratorApi, OrchestratorDeps } from './orchStore'

export {
  currentGate, syncStreamGate, ECHO_GUARD_MS, inEchoGuard, playBeep,
  stopBargeIn, bargeInEnabled,
} from './gate'

export {
  DONE_RESET_MS, followupWindowMs, armFollowupTimer, clearFollowupTimer,
  clearCommandTimer, clearWaitTimers, listenIdleMs, clearIdleTimer,
  armIdleTimer, resetIdleDeadline, armCommandTimer,
} from './timers'

export { resetFailures, onUploadFailed, breakerAllows } from './breaker'
export { beginTranscribe, endTranscribe } from './transcribe'
export { tryEnterCallFromStandby, abandonPendingQuestion } from './callEntry'
