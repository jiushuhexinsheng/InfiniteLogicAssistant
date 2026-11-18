// 拆分自 orchState.ts：上传失败计数与熔断门（当前无调用方，保持导出形状不变）。
// Split from orchState.ts: upload-failure counting and circuit-breaker gate (currently
// uncalled; exports kept unchanged).

import { statusLine } from '../store'
import { st } from './orchStore'

const FAILURE_LIMIT = 3
/** 熔断后的冷静期：期间暂停上传，过后自动恢复一次试探（不再永久静默 ——
 *  断连是间歇性的，永久熔断会让用户以为唤醒彻底坏了，只能手动关开恢复）。
 *  Cooldown after tripping: uploads pause for this long, then one probe is allowed
 *  (no more permanent silence — disconnects are intermittent, and a permanent break
 *  makes wake look dead until manually toggled). */
const BREAKER_COOLDOWN_MS = 60_000

export function resetFailures() {
  if (st.failures === 0 && !st.breakerTrippedAt) return
  st.failures = 0
  st.breakerTrippedAt = 0
  console.log('[wake] 用户重启监听，失败计数已清零')
}

export function onUploadFailed() {
  st.failures++
  if (st.failures >= FAILURE_LIMIT) {
    st.breakerTrippedAt = Date.now()
    statusLine.value = '⚠️ 云端唤醒暂不可用（已连续失败 3 次），1 分钟后自动重试；关闭再开启唤醒可立即恢复'
    console.warn('[wake] 连续失败达阈值，暂停上传，1 分钟后自动试探恢复')
  }
}

/**
 * 熔断门：是否应放行一次上传。冷静期内拦截；冷静期过后清零计数放行试探。
 * Circuit-breaker gate: whether one upload may proceed. Blocks during the cooldown;
 * after it expires the counter resets and a probe is allowed.
 */
export function breakerAllows(): boolean {
  if (st.failures < FAILURE_LIMIT) return true
  if (Date.now() - st.breakerTrippedAt >= BREAKER_COOLDOWN_MS) {
    st.failures = 0
    st.breakerTrippedAt = 0
    statusLine.value = ''
    console.log('[wake] 熔断冷静期结束，恢复上传试探')
    return true
  }
  return false
}
