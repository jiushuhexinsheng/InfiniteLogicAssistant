import { api } from '../../api'
import { formatError } from '../../errors'
import { state, messages } from './store'
import type { Block } from '../../blocks/types'
import { abortChat } from './useChat'

/** 在消息块里找工具块（按 call_id / 块 id）。Find a tool block by call_id / block id. */
function findToolBlock(id: string): Block | undefined {
  for (const msg of messages.value) {
    for (const b of msg.blocks || []) {
      if (b.type === 'tool' && (b.payload.call_id === id || b.id === id)) return b
    }
  }
  return undefined
}

/** 工具重试：失败的工具走后端真实重跑，再用修正结果续一轮对话。
 *  Tool retry: failed tool reruns on backend, then continues conversation with corrected result.
 *  @param id - 工具调用 ID。Tool call ID. */
export async function retryTool(id: string) {
  const blk = findToolBlock(id)
  if (!blk) return

  blk.payload.status = 'running'
  blk.payload.output = ''
  blk.payload.output_preview = ''
  state.value = 'tool_calling'

  const startTs = Date.now()
  try {
    // 高风险工具（后端返回 needs_confirm）先弹确认，确认后再带 confirm 重调。
    // High-risk tools (backend returns needs_confirm) prompt confirmation first, then re-invoke with confirm flag.
    let r = await api.callTool(blk.payload.name, blk.payload.args || {})
    if (r.needs_confirm) {
      const ok = window.confirm(`确认执行高风险工具「${blk.payload.name}」？\n参数：${JSON.stringify(blk.payload.args || {})}`)
      r = ok
        ? await api.callTool(blk.payload.name, blk.payload.args || {}, true)
        : { ok: false, status: 'error', error: '用户取消确认' }
    }
    if (r.ok) {
      blk.payload.status = r.status === 'ok' ? 'ok' : 'error'
      blk.payload.output = r.output || ''
      blk.payload.output_preview = (r.output || '').slice(0, 500)
    } else {
      blk.payload.status = 'error'
      blk.payload.output = r.error || '执行失败'
      blk.payload.output_preview = blk.payload.output
    }
  } catch (e) {
    blk.payload.status = 'error'
    // 兜底用领域化的「执行失败」，比通用的「未知错误」更能说明发生了什么
    // Fall back to the domain-specific "执行失败", which conveys more than a generic message.
    blk.payload.output = formatError(e, '执行失败')
    blk.payload.output_preview = blk.payload.output
  }
  blk.payload.duration_ms = Date.now() - startTs
  // 不再自动续轮：编排管线按新话语驱动，用户可发「继续」等新话语，历史随 messages 种子带入。
  // No longer auto-continue: orchestration pipeline driven by new utterances, users can send "continue" etc., history seeded with messages.
}

/** 工具/回复取消：中止后端 SSE 流，本地将运行中的步骤标记为已取消。
 *  Tool/reply cancel: abort backend SSE stream, locally mark running steps as cancelled.
 *  @param id - 工具调用 ID。Tool call ID. */
export function cancelTool(id: string) {
  abortChat()
  const blk = findToolBlock(id)
  if (blk && (blk.payload.status === 'running' || !blk.payload.status)) {
    blk.payload.status = 'cancelled'
    blk.payload.output = '已取消'
    blk.payload.output_preview = '已取消'
  }
}
