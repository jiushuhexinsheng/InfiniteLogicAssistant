/**
 * 流式识别显示状态：interim（正在识别）与 final（识别完成）的双缓冲。
 *
 * Streaming-transcript display state: the interim/final double buffer.
 *
 * 设计对应参考文档的 committedText / interimText：中间稿**原地替换**，定稿后清空；
 * 最终文本是否进聊天记录由 streamFlow 的分流决定（作答/指令/通话才进）。
 *
 * Mirrors the reference doc's committedText / interimText: the interim is replaced in
 * place and cleared on final; whether the final enters the chat record is decided by
 * streamFlow (answers/commands/call only).
 */
import { ref } from 'vue'
import { partialText, statusLine, state } from './store'

export type TranscriptStatus = 'idle' | 'recognizing' | 'finalized'

/** 流式会话的粗粒度阶段（用于顶部/迷你条的状态与错误提示）。
 *  Coarse streaming-session phase (drives the status/error surfaces). */
export type StreamPhase = 'idle' | 'loading' | 'ready' | 'recognizing' | 'finalized' | 'error'

/** 当前流式阶段。Current streaming phase. */
export const streamPhase = ref<StreamPhase>('idle')
/** 最近一次流式错误（保持到用户下一次启动/切换）。Latest streaming error (kept until retry). */
export const streamError = ref('')

/** 识别结果去向（HUD）：idle / ghost（未进入对话）/ accepted（已作为 LLM 输入）。 */
export type HudOutcome = 'idle' | 'ghost' | 'accepted'
export const hudOutcome = ref<HudOutcome>('idle')
let hudTimer: ReturnType<typeof setTimeout> | null = null

/** 标记本条定稿已被接受为 LLM 输入（短暂显示绿色「→ LLM」）。 */
export function markHudAccepted(): void {
  if (hudTimer) { clearTimeout(hudTimer); hudTimer = null }
  hudOutcome.value = 'accepted'
  hudTimer = setTimeout(() => {
    if (hudOutcome.value === 'accepted') hudOutcome.value = 'idle'
  }, 2000)
}

/** 设置阶段；error 时保留原因，其他阶段清空错误。Set the phase; keep the reason on error. */
export function setStreamPhase(phase: StreamPhase, error = '') {
  streamPhase.value = phase
  streamError.value = phase === 'error' ? error : ''
}

/** 当前识别会话的显示状态。Display state of the current recognition session. */
export interface LiveTranscript {
  /** 当前段号（服务端递增）。Current segment id (server-incremented). */
  segmentId: number
  /** 正在识别的中间稿。The in-flight interim transcript. */
  interim: string
  /** idle / recognizing / finalized。 */
  status: TranscriptStatus
  /** 最近一次定稿文本。The latest finalized text. */
  finalText: string
  /** 未进聊天记录的旁白（短暂显示后消失）。Heard-but-discarded text (brief ghost). */
  ghostText: string
  /** local / cloud。 */
  engine: string
  /** 服务端唤醒判定。Server wake verdict. */
  wake: Record<string, unknown> | null
}

/** 模块级单例（与 store 的其余状态同模式）。Module-level singleton (same pattern as store). */
export const liveTranscript = ref<LiveTranscript>({
  segmentId: 0,
  interim: '',
  status: 'idle',
  finalText: '',
  ghostText: '',
  engine: '',
  wake: null,
})

const REST_STATES = ['listening', 'recording', 'awaiting_answer', 'followup', 'standby']
let finalTimer: ReturnType<typeof setTimeout> | null = null

/** 开始一段识别：清空中间稿并进入「正在识别」。Begin a segment. */
export function beginRecognition(segmentId = 0) {
  if (finalTimer) { clearTimeout(finalTimer); finalTimer = null }
  if (hudTimer) { clearTimeout(hudTimer); hudTimer = null }
  hudOutcome.value = 'idle'
  setStreamPhase('recognizing')
  liveTranscript.value = {
    ...liveTranscript.value,
    segmentId,
    interim: '',
    status: 'recognizing',
    finalText: '',
    ghostText: '',
    wake: null,
  }
  partialText.value = ''
  if (REST_STATES.includes(state.value)) state.value = 'transcribing'
}

/** 中间稿原地替换。Replace the interim in place. */
export function setInterim(text: string, segmentId = 0) {
  if (!text) return
  liveTranscript.value = {
    ...liveTranscript.value,
    segmentId,
    interim: text,
    status: 'recognizing',
  }
  partialText.value = text
  if (state.value !== 'transcribing') state.value = 'transcribing'
}

/**
 * 定稿：清中间稿、短暂显示「识别完成」。
 * Finalize: clear the interim and flash "识别完成".
 *
 * @param text 定稿文本。Final text.
 * @param segmentId 段号。Segment id.
 * @param extras 引擎与唤醒判定。Engine and wake verdict.
 */
export function finalizeTranscript(
  text: string,
  segmentId = 0,
  extras: { engine?: string; wake?: Record<string, unknown> | null } = {},
) {
  if (finalTimer) { clearTimeout(finalTimer); finalTimer = null }
  liveTranscript.value = {
    ...liveTranscript.value,
    segmentId,
    interim: '',
    status: 'finalized',
    finalText: text,
    ghostText: '',
    engine: extras.engine || '',
    wake: extras.wake ?? null,
  }
  partialText.value = ''
  statusLine.value = text ? '识别完成' : '没听清，请再说一次'
  setStreamPhase('finalized')
  finalTimer = setTimeout(() => {
    if (liveTranscript.value.status === 'finalized') {
      liveTranscript.value = { ...liveTranscript.value, status: 'idle', ghostText: '' }
      setStreamPhase('ready')
      if (hudOutcome.value === 'ghost') hudOutcome.value = 'idle'
    }
  }, 1500)
}

/** 未进聊天记录的定稿（旁白/未唤醒）短暂显示为 ghost。Show a discarded final briefly. */
export function showGhost(text: string) {
  if (!text) return
  if (hudTimer) { clearTimeout(hudTimer); hudTimer = null }
  hudOutcome.value = 'ghost'
  liveTranscript.value = {
    ...liveTranscript.value,
    status: 'finalized',
    finalText: text,
    ghostText: text,
  }
}

/** 清空全部识别显示状态（关麦/出错）。Clear every transcript surface. */
export function clearTranscript() {
  if (finalTimer) { clearTimeout(finalTimer); finalTimer = null }
  if (hudTimer) { clearTimeout(hudTimer); hudTimer = null }
  hudOutcome.value = 'idle'
  liveTranscript.value = {
    segmentId: 0,
    interim: '',
    status: 'idle',
    finalText: '',
    ghostText: '',
    engine: '',
    wake: null,
  }
  partialText.value = ''
}
