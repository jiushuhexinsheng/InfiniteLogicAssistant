// 拆分自 orchState.ts：只保留共享状态与依赖注入，其余职责按域拆到同级模块。
// Split from orchState.ts: shared mutable state and dependency injection only; other
// responsibilities live in sibling modules by domain.

import type { Ref } from 'vue'
import type { PendingQuestion } from '../store'
import type { StreamGate, VoiceStreamHandle } from '../stream/streamClient'
import type { BargeInMonitor } from '../bargeIn'

// ── 可注入依赖（由 useWakeWord.ts 注入）──

/** 编排器仍需的少量 API（其余语音调用已由 WebSocket 会话承担）。 */
export interface OrchestratorApi {
  /** 停止任务并弃掉待答问题（T1 stop 端点毒丸）。Stop the task and abandon the pending question. */
  stopTask?(sid: string): Promise<unknown>
  /** 退出通话会话（静止超时自动退通话用）。Exit the call session. */
  callStop?(opts?: { call_id?: string }): Promise<unknown>
}

/** 可注入依赖集合。Injectable dependencies. */
export interface OrchestratorDeps {
  api: OrchestratorApi
  sendText: (text: string) => void
  sendAnswer: (text: string, choice?: string, source?: string, question?: PendingQuestion | null) => Promise<void> | void
  speaking: Ref<boolean>
  /** 停止播报（barge-in 命中时掐断 TTS；由 useTts 注入，缺省无操作）。
   *  Stop playback (cut the TTS on a barge-in hit; injected by useTts, no-op if absent). */
  stopSpeak?: (reason?: 'ui' | 'new_turn' | 'barge_in') => void
  /** 静待中裸唤醒 → 进入通话聆听（useWakeWord 注入 callMode.enterCallFromWake；
   *  返回 false/缺省时调用方回退指令窗语义，不丢唤醒）。
   *  Bare wake in standby → enter call listening (useWakeWord injects
   *  callMode.enterCallFromWake; a false/absent return falls back to the command-window
   *  semantics so the wake is never lost). */
  enterCall?(): Promise<boolean>
}

/** 编排器全部模块级可变状态（单一实例，各拆分模块共享同一引用）。
 *  All module-level mutable state (one instance shared by every split module). */
export const st: {
  deps: OrchestratorDeps | null
  /** 流式语音会话（唯一麦克风链路）。The streaming voice session (the only mic path). */
  voiceStream: VoiceStreamHandle | null
  awaitingCommand: boolean
  failures: number
  breakerTrippedAt: number
  lastUploadAt: number
  listenGen: number
  startingWake: boolean
  commandTimer: ReturnType<typeof setTimeout> | null
  resetTimer: ReturnType<typeof setTimeout> | null
  followupTimer: ReturnType<typeof setTimeout> | null
  idleTimer: ReturnType<typeof setTimeout> | null
  idleDeadline: number
  echoGuardUntil: number
  turnToken: number
  bargeMonitor: BargeInMonitor | null
  /** 续聊窗口是否仍有效（transcribing 等中间态也要保持 open 闸门）。
   *  Whether the follow-up window is still active (intermediate transcribing states
   *  must keep the gate open). */
  followupActive: boolean
} = {
  deps: null,
  voiceStream: null,
  awaitingCommand: false,
  failures: 0,
  breakerTrippedAt: 0,
  lastUploadAt: 0,
  listenGen: 0,
  startingWake: false,
  commandTimer: null,
  resetTimer: null,
  followupTimer: null,
  idleTimer: null,
  idleDeadline: 0,
  echoGuardUntil: 0,
  turnToken: 0,
  bargeMonitor: null,
  followupActive: false,
}

/**
 * 注入编排器依赖。
 *
 * Configure orchestrator dependencies.
 *
 * 由 `useWakeWord.ts` 在模块加载时调用一次。
 * Called once by `useWakeWord.ts` at module load.
 *
 * @param d 依赖集合。The dependencies.
 */
export function configureOrchestrator(d: OrchestratorDeps) {
  st.deps = d
}
