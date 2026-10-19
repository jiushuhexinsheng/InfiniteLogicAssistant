/**
 * 通话漏斗 miss 的可见文案（stage/reason → 人话）。
 *
 * Visible copy for call-funnel misses (stage/reason → human text).
 */
const MISS_STATUS: Record<string, string> = {
  'l0/no_session': '通话会话已过期，请重新双击进入',
  'l0/echo': '助手播报中，语音已忽略',
  'l0/too_short': '说话太短，未识别',
  'l0/low_rms': '声音太小，没听清',
  'l0/unfocused': '窗口未聚焦，语音未处理',
  'l1/empty': '没听清内容，请再说一次',
  'l1/too_short': '说话太短，未识别',
  'l1/filler': '只有语气词，未识别',
  'l2/bystander': '未识别为指令（旁人/背景）',
  'l2/unsure': '没听懂这段话，请再说一次',
  error: '语音判定出错，请重试',
}

/**
 * 按 stage/reason 得到 miss 文案；未知组合给中性兜底。
 * Miss copy from stage/reason; unknown pairs fall back to a neutral line.
 */
export function missStatusLine(stage?: string, reason?: string): string {
  if (!reason) return '未识别'
  const key = stage ? `${stage}/${reason}` : reason
  return MISS_STATUS[key] ?? MISS_STATUS[reason] ?? '未识别'
}
