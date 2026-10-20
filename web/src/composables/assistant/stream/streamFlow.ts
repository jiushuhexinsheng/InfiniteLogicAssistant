/**
 * 流式 final → 既有分流（作答 / 通话 / 指令 / 续聊 / 唤醒）。
 *
 * Streaming final → the existing routing (answer / call / command / follow-up / wake).
 *
 * 服务端已经给出文本与唤醒判定（KWS + 拼音），前端不再上传音频、不再重复调
 * `/voice/wake`；这里只做状态机与聊天记录。
 *
 * The server already produced the text and wake verdict (KWS + pinyin); the frontend no
 * longer uploads audio or re-calls `/voice/wake`. This module only drives the state
 * machine and the chat record.
 */
import { api } from '../../../api'
import {
  state, statusLine, pendingQuestion, callActive, wakeEnabled, inOpenWindow, markTurnEnded,
} from '../store'
import type { AsstState } from '../store'
import { matchOption } from '../answerMatch'
import { enterWakeCooldown } from '../wakeMatch'
import {
  st, playBeep, armCommandTimer, clearCommandTimer, clearFollowupTimer,
  inEchoGuard, abandonPendingQuestion, tryEnterCallFromStandby,
} from '../wake/orchState'
import {
  beginRecognition, setInterim, finalizeTranscript, showGhost, setStreamPhase,
} from '../storeTranscript'
import { missStatusLine } from './missStatus'

/** 服务端事件的最小形状。Minimal shape of a server event. */
export interface StreamEvent {
  type: string
  [key: string]: unknown
}

/** 一段识别开始前的助手状态（final 时据此恢复分流语义）。State before recognition. */
let baseState: AsstState | null = null

function restoreBase(): void {
  if (state.value !== 'transcribing') return
  state.value = baseState
    ?? (callActive.value ? 'listening' : wakeEnabled.value ? 'listening' : 'idle')
}

/** 处理一条服务端事件。Handle one server event. */
export async function handleStreamEvent(ev: StreamEvent): Promise<void> {
  switch (ev.type) {
    case 'ready':
      setStreamPhase('ready')
      return
    case 'vad':
      if (ev.event === 'speech_start') {
        if (state.value !== 'transcribing') baseState = state.value
        beginRecognition(Number(ev.segment_id || 0))
      }
      return
    case 'status':
      if (ev.state === 'recognizing') {
        if (state.value !== 'transcribing') baseState = state.value
        beginRecognition(Number(ev.segment_id || 0))
      }
      return
    case 'partial':
      setInterim(String(ev.text || ''), Number(ev.segment_id || 0))
      return
    case 'final':
      await handleFinal(ev)
      return
    case 'error': {
      const message = String(ev.message || '语音识别失败')
      statusLine.value = message
      setStreamPhase('error', message)
      restoreBase()
      return
    }
    default:
      return
  }
}

async function handleFinal(ev: StreamEvent): Promise<void> {
  const text = String(ev.text || '').trim()
  const wake = (ev.wake || {}) as { matched?: boolean; command?: string }
  finalizeTranscript(text, Number(ev.segment_id || 0), {
    engine: String(ev.engine || ''),
    wake: (ev.wake || null) as Record<string, unknown> | null,
  })
  restoreBase()
  if (!text) return
  if (inEchoGuard()) return

  // 1) 待答问题：唤醒词优先弃题，否则作答。Pending question: wake abandons, else answers.
  const pq = pendingQuestion.value
  if (pq) {
    st.turnToken++
    if (wake.matched) {
      abandonPendingQuestion()
      if (wake.command) {
        st.turnToken++
        enterWakeCooldown()
        st.deps?.sendText(wake.command)
      } else {
        enterCommandWindow()
      }
      return
    }
    const hit = matchOption(text, pq.options)
    await st.deps?.sendAnswer(hit ? '' : text, hit?.value, 'voice', pq)
    return
  }

  // 2) 通话：文本判定（L0/L1/L2）后再送编排。Call: text judge then orchestrate.
  if (callActive.value) {
    await judgeCall(text, ev)
    return
  }

  // 3) 等指令窗：整句就是指令。Command window: the whole sentence is the command.
  if (st.awaitingCommand) {
    st.turnToken++
    if (text) {
      st.awaitingCommand = false
      clearCommandTimer()
      statusLine.value = ''
      st.failures = 0
      enterWakeCooldown()
      st.deps?.sendText(text)
    } else {
      armCommandTimer()
    }
    return
  }

  // 4) 续聊窗口：命中唤醒词照常处理，否则整句当新指令。
  // Follow-up window: a wake hit behaves normally; otherwise the whole sentence is a command.
  if (baseState === 'followup') {
    st.turnToken++
    if (wake.matched) {
      if (wake.command) {
        enterWakeCooldown()
        clearFollowupTimer()
        st.deps?.sendText(wake.command)
      } else {
        enterCommandWindow()
      }
      return
    }
    clearFollowupTimer()
    st.deps?.sendText(text)
    return
  }

  // 5) 普通唤醒：命中且带指令 → 执行；裸唤醒 → 提示音 + 指令窗；未命中 → ghost。
  if (wake.matched) {
    if (wake.command) {
      st.turnToken++
      enterWakeCooldown()
      st.deps?.sendText(wake.command)
      return
    }
    if (await tryEnterCallFromStandby()) return
    enterCommandWindow()
    return
  }

  showGhost(text)
  statusLine.value = '未识别到唤醒词'
}

function enterCommandWindow(): void {
  st.awaitingCommand = true
  statusLine.value = '已唤醒，请说指令…'
  if (state.value === 'listening' || state.value === 'standby') state.value = 'recording'
  playBeep()
  armCommandTimer()
}

async function judgeCall(text: string, ev: StreamEvent): Promise<void> {
  const r = await api.callJudge(text, {
    durationMs: Number(ev.duration_ms || 0),
    rms: Number(ev.rms ?? 1),
    tabFocused: typeof document !== 'undefined' && document.hasFocus(),
    inOpenWindow: inOpenWindow(),
  }).catch((): { ok?: boolean; hit?: boolean; text?: string; stage?: string; reason?: string } => ({ ok: false }))
  if (r?.ok && r.hit && r.text) {
    st.turnToken++
    markTurnEnded()
    if (state.value === 'recording') state.value = 'listening'
    statusLine.value = ''
    st.deps?.sendText(r.text)
  } else {
    statusLine.value = r?.ok ? missStatusLine(r.stage, r.reason) : '语音判定失败，请重试'
  }
}
