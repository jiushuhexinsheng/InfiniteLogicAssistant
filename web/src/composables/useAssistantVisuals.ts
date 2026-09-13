import type { AsstState } from './useAssistant'

/** 状态视觉配置接口。State visual configuration interface. */
export interface StateVisual {
  /** 状态图标名称。State icon name. */
  icon: string
  /** 状态标签，可以是字符串或接收关键字的函数。State label, can be a string or a function that receives a keyword. */
  label: string | ((kw: string) => string)
  /** 状态颜色（十六进制）。State color (hexadecimal). */
  color: string
  /** 视觉效果类名。Visual effect class name. */
  fx: string
  /** 渐变类型：品牌色或彩虹色。Gradient type: brand or rainbow. */
  grad: 'brand' | 'rainbow'
}

/** 状态视觉映射表，为每个助手状态定义视觉配置。State visual mapping table, defines visual configuration for each assistant state. */
export const STATE_VISUALS: Record<AsstState, StateVisual> = {
  idle:         { icon: 'wave',       label: '双击唤醒',                  color: '#6b7280', fx: 'fx-idle',          grad: 'brand' },
  listening:    { icon: 'ear',        label: kw => `聆听中…说"${kw}"`,     color: '#34d399', fx: 'fx-listening',     grad: 'rainbow' },
  awaiting_answer: { icon: 'mic',     label: '请直接说出你的回答…',        color: '#f59e0b', fx: 'fx-recording',     grad: 'rainbow' },
  standby:      { icon: 'ear',        label: kw => `待机中…说"${kw}"继续`, color: '#94a3b8', fx: 'fx-idle',          grad: 'brand' },
  recording:    { icon: 'mic',        label: '录音中…',                   color: '#f87171', fx: 'fx-recording',     grad: 'rainbow' },
  transcribing: { icon: 'sparkles',   label: '识别中…',                   color: '#c084fc', fx: 'fx-transcribing',  grad: 'brand' },
  thinking:     { icon: 'brain',      label: '思考中…',                   color: '#fb923c', fx: 'fx-thinking',      grad: 'brand' },
  tool_calling: { icon: 'wrench',     label: '执行中…',                   color: '#22d3ee', fx: 'fx-tool_calling',  grad: 'brand' },
  responding:   { icon: 'chat',       label: '',                          color: '#818cf8', fx: 'fx-responding',    grad: 'brand' },
  done:         { icon: 'check',      label: '完成',                      color: '#34d399', fx: 'fx-done',          grad: 'brand' },
  error:        { icon: 'alert',      label: '出错了',                    color: '#f87171', fx: 'fx-error',         grad: 'brand' },
}

/** 解析状态标签，如果标签是函数则调用它，否则直接返回。
 *  Resolve state label: if the label is a function, call it; otherwise return directly.
 *  @param v - 状态视觉配置。State visual configuration.
 *  @param kw - 唤醒关键字。Wake keyword.
 *  @returns 解析后的状态标签字符串。Resolved state label string. */
export function resolveStateLabel(v: StateVisual, kw: string): string {
  return typeof v.label === 'function' ? v.label(kw) : v.label
}
