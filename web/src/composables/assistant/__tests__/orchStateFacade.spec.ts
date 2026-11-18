// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'

import * as facade from '../wake/orchState'

/**
 * orchState 拆分后的聚合入口锁：消费方（streamFlow / micControl / watches / useChat /
 * 测试）都从 `wake/orchState` 单点导入，成员一旦改名或漏 re-export 必须在这里变红。
 *
 * Lock for the orchState aggregation layer: every consumer imports from the single
 * `wake/orchState` entry, so a renamed or missing re-export must fail here.
 */
const EXPECTED_EXPORTS = [
  // 状态与依赖注入 / State and DI
  'st', 'configureOrchestrator',
  // 上传闸门与护栏 / Gate and guards
  'currentGate', 'syncStreamGate', 'ECHO_GUARD_MS', 'inEchoGuard', 'playBeep',
  'stopBargeIn', 'bargeInEnabled',
  // 计时器 / Timers
  'DONE_RESET_MS', 'followupWindowMs', 'armFollowupTimer', 'clearFollowupTimer',
  'clearCommandTimer', 'clearWaitTimers', 'listenIdleMs', 'clearIdleTimer',
  'armIdleTimer', 'resetIdleDeadline', 'armCommandTimer',
  // 熔断 / Breaker
  'resetFailures', 'onUploadFailed', 'breakerAllows',
  // 识别中状态 / Transcribing state
  'beginTranscribe', 'endTranscribe',
  // 通话进入与弃题 / Call entry and abandonment
  'tryEnterCallFromStandby', 'abandonPendingQuestion',
] as const

describe('orchState 聚合入口', () => {
  it('保持拆分前的全部导出成员', () => {
    for (const name of EXPECTED_EXPORTS) {
      expect(facade, `missing export: ${name}`).toHaveProperty(name)
    }
  })

  it('st 仍是同一个可变状态对象（单一实例语义）', () => {
    expect(facade.st).toBeTypeOf('object')
    expect(facade.st.followupTimer).toBeNull()
    expect(facade.st.awaitingCommand).toBe(false)
  })

  it('闸门函数返回值合法', () => {
    expect(['wake', 'open']).toContain(facade.currentGate())
  })
})
