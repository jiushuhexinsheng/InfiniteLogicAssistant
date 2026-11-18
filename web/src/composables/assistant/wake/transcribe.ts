// 拆分自 orchState.ts：识别中状态（transcribing）进出。
// Split from orchState.ts: entering/leaving the transcribing state.

import { state } from '../store'
import type { AsstState } from '../store'

const TRANSCRIBABLE: AsstState[] = ['listening', 'awaiting_answer', 'recording', 'followup', 'standby']

export function beginTranscribe(): AsstState | null {
  if (!TRANSCRIBABLE.includes(state.value)) return null
  const prev = state.value
  state.value = 'transcribing'
  return prev
}

export function endTranscribe(prev: AsstState | null) {
  if (prev && state.value === 'transcribing') state.value = prev
}
