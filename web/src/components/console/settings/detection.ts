import { ref } from 'vue'
import { api } from '../../../api'
import { notify } from '../../../composables/useToast'
import { formatError } from '../../../errors'
import type { ConnectivityResult, DetectionIssue } from '../../../types'

/**
 * 服务连通性检测与配置校验问题。
 * Service connectivity detection and config validation issues.
 *
 * 2026-10-11 结果呈现改为「toast 弹 3 秒 + 左侧菜单绿点」：内容区顶部的结果条与
 * 卡底结果行删除 —— 检测反馈不该占版面。
 * 2026-10-11 results surface as "3s toast + green dot in the left menu": the top
 * results bar and the per-card result line are gone — test feedback must not take
 * up layout space.
 */

/** 检测中状态标志。Detection in progress flag. */
export const detecting = ref(false)
/** 连通性检测结果（按服务名索引；仅作数据留存，不再渲染顶部条）。
 *  Connectivity results (indexed by service name; kept as data only — the top bar
 *  is no longer rendered). */
export const connResults = ref<Record<string, ConnectivityResult>>({})
/** 配置校验问题列表。Config validation issue list. */
export const issues = ref<DetectionIssue[]>([])

/**
 * 每模块最近一次测试结果（键 = 模块 id 小写）：true=通过（菜单绿点）/ false=失败
 * （绿点熄灭）/ undefined=未测过（回退「密钥已设」判定）。
 * Last test result per module (key = lowercased module id): true = passed (green dot),
 * false = failed (dot off), undefined = never tested (falls back to "key set").
 */
export const testPassed = ref<Record<string, boolean | undefined>>({})

function recordResult(name: string, ok: boolean) {
  testPassed.value = { ...testPassed.value, [name.toLowerCase()]: ok }
}

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
      // 菜单绿点按各模块结果更新 + 一条 3 秒级汇总 toast。
      // Update the menu dots per module + one short summary toast.
      for (const c of r.report.connectivity) recordResult(c.name, c.status === 'ok')
      const bad = r.report.connectivity.filter(c => c.status !== 'ok')
      if (!bad.length) notify.ok(`检测完成：${r.report.connectivity.length} 项全部连通`)
      else notify.err(`检测完成：${bad.map(c => c.name).join('、')} 未通过`)
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
 * 检测单个服务连通性（结果走 toast，成功点亮左侧菜单绿点）。
 * Test a single service (results go through a toast; success lights the left-menu dot).
 *
 * @param name 服务名（LLM / ASR / TTS）。Service name (LLM / ASR / TTS).
 */
export async function detectOne(name: string) {
  detecting.value = true
  try {
    const r = await api.getDetection()
    if (r.ok) {
      const c = r.report.connectivity.find((x) => x.name === name)
      if (c) {
        connResults.value = { ...connResults.value, [name]: c }
        const latency = c.latency_ms != null ? `（${c.latency_ms}ms）` : ''
        if (c.status === 'ok') {
          recordResult(name, true)
          notify.ok(`${name} 连通正常${latency}`)
        } else if (c.status === 'skip') {
          recordResult(name, false)
          notify.info(`${name} 未配置，已跳过`)
        } else {
          recordResult(name, false)
          notify.err(`${name} 连通失败${c.detail ? '：' + c.detail : ''}`)
        }
      }
    } else {
      notify.err(`${name} 检测失败：` + ((r as any)?.error || ''))
    }
  } catch (e) {
    notify.err(`${name} 检测失败：` + formatError(e))
  } finally {
    detecting.value = false
  }
}
