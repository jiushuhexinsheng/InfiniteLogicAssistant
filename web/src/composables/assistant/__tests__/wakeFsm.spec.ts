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

  /** 待答超时（用户全程未说话）→ 待机。An answer-wait timeout (the user never spoke) enters standby. */
  it('answer_timeout 在待答态 → standby', () => {
    expect(nextState('awaiting_answer', 'answer_timeout')).toBe('standby')
  })

  /** 待机时再唤醒 → 回到待答（续答本题），而不是开新一轮。
   *  Waking from standby returns to awaiting the answer (resuming this question). */
  it('待机态 wake_detected → awaiting_answer（续答本题）', () => {
    expect(nextState('standby', 'wake_detected')).toBe('awaiting_answer')
  })

  /** 普通 listening 态唤醒维持既有权为（由调用方置 recording）—— 回归。
   *  Waking from plain listening keeps existing behaviour (the caller sets recording). */
  it('listening 态 wake_detected 不改状态（回归）', () => {
    expect(nextState('listening', 'wake_detected')).toBe('listening')
  })

  /** 待答态检测到语音 → 状态不变（交回既有 VAD 静音逻辑收尾）。
   *  Speech starting while awaiting an answer leaves the state unchanged; the existing VAD
   *  silence logic finishes the recording. */
  it('待答态 speech_started 保持 awaiting_answer', () => {
    expect(nextState('awaiting_answer', 'speech_started')).toBe('awaiting_answer')
  })

  /** 关了唤醒开关 → idle。Turning the wake switch off goes idle. */
  it('wake_toggled_off → idle', () => {
    expect(nextState('standby', 'wake_toggled_off')).toBe('idle')
    expect(nextState('awaiting_answer', 'wake_toggled_off')).toBe('idle')
    expect(nextState('listening', 'wake_toggled_off')).toBe('idle')
  })

  /** 无关组合保持不变，不抛错。Unrelated combinations keep the current state and do not throw. */
  it('无关事件不改变状态', () => {
    expect(nextState('idle', 'speech_started')).toBe('idle')
    expect(nextState('thinking', 'answer_timeout')).toBe('thinking')
    expect(nextState('recording', 'question_ready')).toBe('recording')
    expect(nextState('listening', 'answer_timeout')).toBe('listening')
  })
})
