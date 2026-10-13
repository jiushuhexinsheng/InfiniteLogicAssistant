import { ref } from 'vue'
import { api } from '../api'

/**
 * 后端连通性探测：一次 ping + 最近一次延迟。
 *
 * 原先 `ServiceStatusCard`（起始页「实时状态」卡）与 `ConsoleStatus`（控制台「状态」页）
 * 各自写了一份**逐行相同**的实现；抽到这里，两处共用。
 *
 * Backend reachability probe: one ping plus the latest latency.
 *
 * `ServiceStatusCard` (the start page's 实时状态 card) and `ConsoleStatus` (the console's 状态
 * tab) each carried a **line-for-line identical** copy; this is the single home for both.
 *
 * 轮询节奏**不在这里** —— 两处的需求不同（控制台按 15s 定时轮询，起始页只在挂载时探一次），
 * 由调用方自己管 `setInterval` / `onUnmounted`。
 * The polling cadence deliberately stays **out** of here — the two callers differ (the console
 * polls every 15s; the start page probes once on mount), so each owns its own `setInterval` /
 * `onUnmounted`.
 *
 * @returns ping 是否成功、最近一次延迟(ms，失败为 null)、手动触发探测的函数。
 *          Whether the ping succeeded, the latest latency in ms (null on failure), and a manual trigger.
 */
export function usePing() {
  /** 后端 ping 是否成功。Whether backend ping succeeded. */
  const pingOk = ref(false)
  /** 后端 ping 延迟（毫秒）。Backend ping latency (ms). */
  const pingMs = ref<number | null>(null)

  /** 执行一次后端 ping 并记录延迟；失败时清空延迟并标记不可达。
   *  Perform one backend ping and record latency; on failure clear the latency and mark unreachable. */
  async function checkPing() {
    try {
      const t0 = performance.now()
      const r = await api.ping()
      pingMs.value = Math.round(performance.now() - t0)
      pingOk.value = r.ok === true
    } catch {
      pingOk.value = false
      pingMs.value = null
    }
  }

  return { pingOk, pingMs, checkPing }
}
