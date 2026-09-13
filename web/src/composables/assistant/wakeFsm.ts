import type { AsstState } from './store'

/** 唤醒状态机的事件。Events of the wake state machine. */
export type WakeEvent =
  /** 提问就绪（已被播报）→ 应自动开录等待作答。A question is ready (already spoken). */
  | 'question_ready'
  /** 本次录音里首次检测到语音。Speech was first detected in this recording. */
  | 'speech_started'
  /** 本次录音正常结束（有待转写内容）。The recording finished normally. */
  | 'speech_done'
  /** 等待作答超时（全程未说话）。The answer wait timed out (no speech at all). */
  | 'answer_timeout'
  /** 唤醒词命中。The wake word fired. */
  | 'wake_detected'
  /** 唤醒功能被关闭。The wake feature was switched off. */
  | 'wake_toggled_off'

/**
 * 唤醒状态机迁移表。
 *
 * **只处理与「等待作答」相关的迁移**，其余组合原样返回当前状态 —— 这样它不会与既有的
 * 散落赋值冲突，接入时可以逐处替换而非一次性重写整个 useWakeWord。
 *
 * 抽成纯函数是因为真实录音路径依赖 MediaRecorder/AudioContext，jsdom 里跑不了；
 * 决策与副作用分离后，迁移可以穷尽测试。
 *
 * Wake state-machine transition table.
 *
 * It **only covers transitions related to awaiting an answer**; every other combination
 * returns the current state unchanged, so it can be wired in incrementally instead of
 * forcing a rewrite of the scattered assignments in useWakeWord. It is a pure function
 * because the real recording path needs MediaRecorder/AudioContext, unavailable under
 * jsdom; splitting the decision from the effects makes the transitions exhaustively
 * testable.
 *
 * @param current 当前状态。The current state.
 * @param event 触发事件。The triggering event.
 * @returns 迁移后的状态。The resulting state.
 */
export function nextState(current: AsstState, event: WakeEvent): AsstState {
  if (event === 'wake_toggled_off') return 'idle'

  switch (event) {
    case 'question_ready':
      // 提问已播报完 → 自动进入待答（不必再说唤醒词）。
      // 只从「助手刚说完话」的几个状态进入，避免打断正在录音/转写的流程。
      // The question has been spoken → start awaiting the answer automatically. Only from
      // states where the assistant has just finished speaking, so an in-flight recording
      // or transcription is not interrupted.
      return current === 'responding' || current === 'thinking' || current === 'done'
        ? 'awaiting_answer'
        : current

    case 'answer_timeout':
      // 只有待答态的超时才进待机；其它状态的超时与本题无关。
      // Only the answer-wait timeout enters standby; other timeouts are unrelated.
      return current === 'awaiting_answer' ? 'standby' : current

    case 'wake_detected':
      // 待机态唤醒 → 续答本题；其余态维持既有行为（由调用方置 recording）。
      // Waking from standby resumes this question; other states keep existing behaviour.
      return current === 'standby' ? 'awaiting_answer' : current

    case 'speech_started':
      // 待答态检测到语音后交回既有 VAD 静音逻辑收尾，状态不变。
      // Once speech starts, the existing VAD silence logic finishes the recording.
      return current

    case 'speech_done':
      return current
  }
}
