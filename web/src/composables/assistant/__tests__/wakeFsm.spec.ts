import { describe, expect, it } from 'vitest'
import { nextState } from '../wakeFsm'

/**
 * 唤醒状态机迁移表（纯函数）。
 *
 * 抽出来是因为真实录音路径依赖 MediaRecorder/AudioContext，jsdom 里跑不了；
 * 迁移决策与副作用分开后，决策可以穷尽测试。
 *
 * The wake state machine transition table (a pure function). It is extracted because the
 * real recording path needs MediaRecorder/AudioContext, unavailable under jsdom; splitting
 * the decision from the effects makes the decision exhaustively testable.
 */
describe('wakeFsm 迁移表', () => {
  /** 提问就绪 → 进入待答（自动开录）。A ready question moves to awaiting an answer. */
  it('question_ready → awaiting_answer', () => {
    expect(nextState('responding', 'question_ready')).toBe('awaiting_answer')
    expect(nextState('thinking', 'question_ready')).toBe('awaiting_answer')
    expect(nextState('done', 'question_ready')).toBe('awaiting_answer')
  })

  // answer_timeout / wake_detected 迁移随「取消限时回答」删除（回答永不限时、standby
  // 整套移除）—— 行为回归由 useWakeWord 的「待答永不超时」用例守住。
  // The answer_timeout / wake_detected transitions went away with the unlimited answer
  // window (no timeouts, standby removed entirely) — behaviour is pinned by
  // useWakeWord's "answers never time out" case.

  /** 待答态检测到语音 → 状态不变（交回既有 VAD 静音逻辑收尾）。
   *  Speech starting while awaiting an answer leaves the state unchanged; the existing VAD
   *  silence logic finishes the recording. */
  it('待答态 speech_started 保持 awaiting_answer', () => {
    expect(nextState('awaiting_answer', 'speech_started')).toBe('awaiting_answer')
  })

  /** 关了唤醒开关 → idle。Turning the wake switch off goes idle. */
  it('wake_toggled_off → idle', () => {
    expect(nextState('awaiting_answer', 'wake_toggled_off')).toBe('idle')
    expect(nextState('listening', 'wake_toggled_off')).toBe('idle')
  })

  /** 无关组合保持不变，不抛错。Unrelated combinations keep the current state and do not throw. */
  it('无关事件不改变状态', () => {
    expect(nextState('idle', 'speech_started')).toBe('idle')
    expect(nextState('recording', 'question_ready')).toBe('recording')
    expect(nextState('listening', 'followup_open')).toBe('listening')
  })

  // ── 续聊窗口（docs/designs/03-A）──

  /** 只有回合结束态开窗；其余态开窗会截断在途流程（回归）。
   *  Only turn-ended states open the window; elsewhere it would cut an in-flight flow. */
  it('followup_open：done/error → followup，其余不动', () => {
    expect(nextState('done', 'followup_open')).toBe('followup')
    expect(nextState('error', 'followup_open')).toBe('followup')
    expect(nextState('listening', 'followup_open')).toBe('listening')
    expect(nextState('transcribing', 'followup_open')).toBe('transcribing')
  })

  /** 到期只在窗口态生效（陈旧定时器不得把别的状态踢回 listening）。
   *  Expiry only applies inside the window (a stale timer must not kick any other state). */
  it('followup_expire：followup → listening，其余不动', () => {
    expect(nextState('followup', 'followup_expire')).toBe('listening')
    expect(nextState('thinking', 'followup_expire')).toBe('thinking')
    expect(nextState('awaiting_answer', 'followup_expire')).toBe('awaiting_answer')
  })

  /** 窗口内插播的问题立即可答。A question arriving inside the window is answerable at once. */
  it('followup 态 question_ready → awaiting_answer', () => {
    expect(nextState('followup', 'question_ready')).toBe('awaiting_answer')
  })
})
