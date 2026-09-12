import { ref } from 'vue'
import { api } from '../../../api'
import { notify } from '../../../composables/useToast'
import { formatError } from '../../../errors'
import type { ConnectivityResult, DetectionIssue } from '../../../types'

/**
 * 服务连通性检测与配置校验问题。
 * Service connectivity detection and config validation issues.
 */

/** 检测中状态标志。Detection in progress flag. */
export const detecting = ref(false)
/** 连通性检测结果（按服务名索引）。Connectivity results (indexed by service name). */
export const connResults = ref<Record<string, ConnectivityResult>>({})
/** 配置校验问题列表。Config validation issues. */
export const issues = ref<DetectionIssue[]>([])

/**
 * 检测全部服务连通性。
 * Test connectivity for all services.
 */
export async function detectAll() {
  detecting.value = true
  issues.value = []
  try {
    const r = await api.getDetection()
    if (r.ok && r.report) {
      connResults.value = Object.fromEntries(r.report.connectivity.map((c) => [c.name, c]))
      issues.value = r.report.config.issues
    } else {
      notify.err('检测失败：' + ((r as any)?.error || ''))
    }
  } catch (e) {
    notify.err('检测失败：' + formatError(e))
  } finally {
    detecting.value = false
  }
}

/**
 * 检测单个服务连通性。
 * Test connectivity for a single service.
 *
 * @param name 服务名（LLM / ASR / TTS）。Service name (LLM / ASR / TTS).
 */
export async function detectOne(name: string) {
  detecting.value = true
  try {
    const r = await api.getDetection()
    if (r.ok) {
      const c = r.report.connectivity.find((x) => x.name === name)
      if (c) connResults.value = { ...connResults.value, [name]: c }
    }
  } catch {
    /* 静默：单服务检测失败不影响整体显示 / Silent: a single-service failure does not affect the overall display */
  } finally {
    detecting.value = false
  }
}
