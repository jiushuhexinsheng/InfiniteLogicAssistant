import type { AsstState } from './useAssistant'

export interface StateVisual {
  icon: string
  label: string | ((kw: string) => string)
  color: string
  fx: string
  grad: 'brand' | 'rainbow'
}

export const STATE_VISUALS: Record<AsstState, StateVisual> = {
  idle:         { icon: '🤖', label: '双击唤醒',                  color: '#6b7280', fx: 'fx-idle',          grad: 'brand' },
  listening:    { icon: '👂', label: kw => `聆听中…说"${kw}"`,     color: '#34d399', fx: 'fx-listening',     grad: 'rainbow' },
  recording:    { icon: '🔴', label: '录音中…',                   color: '#f87171', fx: 'fx-recording',     grad: 'rainbow' },
  transcribing: { icon: '⏳', label: '识别中…',                   color: '#c084fc', fx: 'fx-transcribing',  grad: 'brand' },
  thinking:     { icon: '🤔', label: '思考中…',                   color: '#fb923c', fx: 'fx-thinking',      grad: 'brand' },
  tool_calling: { icon: '🔧', label: '执行中…',                   color: '#22d3ee', fx: 'fx-tool_calling',  grad: 'brand' },
  responding:   { icon: '💬', label: '',                          color: '#818cf8', fx: 'fx-responding',    grad: 'brand' },
  done:         { icon: '✅', label: '完成',                      color: '#34d399', fx: 'fx-done',          grad: 'brand' },
  error:        { icon: '❌', label: '出错了',                    color: '#f87171', fx: 'fx-error',         grad: 'brand' },
}

export function resolveStateLabel(v: StateVisual, kw: string): string {
  return typeof v.label === 'function' ? v.label(kw) : v.label
}
