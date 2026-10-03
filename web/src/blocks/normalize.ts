/**
 * 事件 → 块流的唯一 reducer —— SSE 事件在块列表上的全部变更规则集中在此
 *
 * content_delta / reasoning_delta 追加或合并进 streaming 块；tool_start/end 按
 * call_id 配对；question / answer / notice / summary / block 直通离散块。
 * 页面与组件不解析事件，只渲染块 —— 这是「不被前端页面束缚」的数据层保证。
 *
 * The single reducer from events to block-stream changes. All mutation rules of
 * SSE events on the block list live here. content_delta / reasoning_delta append
 * into or merge with a streaming block; tool_start/end pair by call_id;
 * question / answer / notice / summary / block pass through as discrete blocks.
 * Pages and components never parse events — they only render blocks.
 */
import type { SseEvent, ToolEndEvent, ToolStartEvent, QuestionEvent, AnswerEvent, BlockEvent } from '../types'
import type { Block } from './types'

/** 生成块 ID（与后端 blk_ 前缀一致）。Generate a block ID (blk_ prefix, consistent with backend). */
export function newBlockId(): string {
  try { return 'blk_' + crypto.randomUUID().replace(/-/g, '').slice(0, 12) }
  catch { return 'blk_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8) }
}

/** 构造块信封（与后端 make_block 对齐：缺省 meta 合并）。Build a block envelope (aligned with backend make_block). */
export function makeBlock(
  type: string,
  payload: Record<string, any>,
  opts: { turnId?: string; agent?: string; meta?: Block['meta'] } = {},
): Block {
  const defaults: Record<string, Block['meta']> = {
    thinking: { tts: 'skip', collapsed: true },
    tool: { tts: 'skip', collapsed: true },
    text: { tts: 'auto', collapsed: false },
    code: { tts: 'skip', collapsed: false },
    image: { tts: 'skip', collapsed: false },
    file: { tts: 'skip', collapsed: false },
    question: { tts: 'full', collapsed: false },
    answer: { tts: 'skip', collapsed: false },
    notice: { tts: 'auto', collapsed: false },
    summary: { tts: 'full', collapsed: false },
    unknown: { tts: 'skip', collapsed: true },
  }
  return {
    v: 1,
    id: newBlockId(),
    type,
    ts: new Date().toISOString(),
    turn_id: opts.turnId,
    agent: opts.agent,
    meta: { ...(defaults[type] ?? { tts: 'skip', collapsed: false }), ...opts.meta },
    payload,
  }
}

/** 找到当前回合仍在流式的指定类型块（用于增量合并）。Find the still-streaming block of a type in this turn. */
function findStreaming(blocks: Block[], type: string): Block | undefined {
  for (let i = blocks.length - 1; i >= 0; i--) {
    const b = blocks[i]
    if (b.type === type && b.meta?.streaming) return b
    if (b.type === type) return undefined  // 已关闭的同类块不合并
  }
  return undefined
}

/**
 * 把作答挂进块列表（原地变更）。SSE answer 事件与 sendAnswer 本地投递共用，
 * 按 qid 幂等去重 —— 两条路径总有一条先到，后到的直接跳过。
 *
 * Attach an answer into the block list (in-place). Shared by the SSE answer event
 * and sendAnswer's local delivery, deduplicated by qid — one path always arrives
 * first; the later one is skipped.
 *
 * 规则（修截图 bug #1「问题和回答分离」）：
 * Rules (fixes screenshot bug #1, Q/A split apart):
 * 1. 已有同 qid 的 answer 块 → 幂等跳过。Same qid already answered → idempotent skip.
 * 2. 配对到 question → 翻 answered，并把答案块插到问题块紧后（问答同卡相邻，
 *    不再落尾部用户气泡拆散卡片）。Paired question → mark answered and splice the
 *    answer right after it (Q and A stay adjacent in the same card, instead of a
 *    trailing user bubble splitting the card apart).
 * 3. source=timeout 的超时作答只翻态、不入块（与旧行为一致，超时答案无文本价值）。
 *    timeout answers only flip status (same as before; no text value to record).
 * 4. choice 展示为选项 label（不写机器值）。choice renders as the option label,
 *    not the machine value.
 * 5. 无配对问题 → 兜底独立入块（保留原行为，如历史回放 / 流已死）。
 *    No paired question → push standalone (original behavior kept: history replay /
 *    dead stream).
 *
 * @param target - 目标块列表。Target block list.
 * @param e - 作答事件（qid/text/choice/source）。The answer event (qid/text/choice/source).
 */
export function attachAnswer(
  target: Block[],
  e: { qid?: string | null; text?: string; choice?: string | null; source?: string | null },
): void {
  if (e.qid && target.some(x => x.type === 'answer' && x.payload.qid === e.qid)) return
  const q = e.qid
    ? target.find(x => x.type === 'question' && x.payload.qid === e.qid)
    : undefined
  if (q) {
    q.payload.status = 'answered'
    if (e.source === 'timeout') return
    const label = e.text
      || (e.choice
        ? (q.payload.options?.find((o: { value?: string }) => o.value === e.choice)?.label || e.choice)
        : '')
    target.splice(target.indexOf(q) + 1, 0, makeBlock('answer', {
      qid: e.qid ?? null,
      text: label,
      choice: e.choice ?? null,
      source: e.source || 'typed',
    }))
    return
  }
  target.push(makeBlock('answer', {
    qid: e.qid ?? null,
    text: e.text || '',
    choice: e.choice ?? null,
    source: e.source || 'typed',
  }))
}

/**
 * 把一个 SSE 事件应用到块列表（原地变更，供响应式数组触发更新）。
 * Apply one SSE event to the block list (in-place, so reactive arrays update).
 *
 * @param ev - SSE 事件。The SSE event.
 * @param target - 目标块列表（当前消息的 blocks）。Target block list (current message's blocks).
 */
export function applyEvent(ev: SseEvent, target: Block[]): void {
  switch (ev.type) {
    case 'content_delta': {
      const b = findStreaming(target, 'text')
      if (b) {
        b.payload.md = (b.payload.md || '') + ev.text
      } else {
        target.push(makeBlock('text', { md: ev.text, variant: 'bubble' }, { meta: { streaming: true } }))
      }
      break
    }
    case 'reasoning_delta': {
      const b = findStreaming(target, 'thinking')
      if (b) {
        b.payload.text = (b.payload.text || '') + ev.text
      } else {
        target.push(makeBlock('thinking', { text: ev.text }, { meta: { streaming: true } }))
      }
      break
    }
    case 'tool_start': {
      const e = ev as ToolStartEvent
      target.push(makeBlock('tool', {
        call_id: e.call_id,
        name: e.name,
        args: e.args || {},
        status: 'running',
      }, { agent: e.agent }))
      break
    }
    case 'tool_end': {
      const e = ev as ToolEndEvent
      // 先按 call_id 配对，无 call_id（旧后端）按「同名 running」配对
      // Pair by call_id first; without one (old backend), pair by name+running.
      const b = [...target].reverse().find(x =>
        x.type === 'tool' && (
          (e.call_id && x.payload.call_id === e.call_id) ||
          (!e.call_id && x.payload.name === e.name && x.payload.status === 'running')
        ))
      if (b) {
        b.payload.status = e.status === 'ok' ? 'ok' : 'error'
        b.payload.output = e.output
        b.payload.output_preview = e.output
        b.payload.truncated = e.truncated
        b.payload.full_len = e.output_len
      }
      break
    }
    case 'question': {
      const e = ev as QuestionEvent
      const b = makeBlock('question', {
        qid: e.qid,
        question: e.question,
        kind: e.kind || 'text',
        options: e.options || [],
        status: 'pending',
      })
      target.push(b)
      break
    }
    case 'answer': {
      attachAnswer(target, ev as AnswerEvent)
      break
    }
    case 'task_state': {
      if (ev.state === 'notify' && ev.text) {
        target.push(makeBlock('notice', { level: 'info', text: ev.text }))
      } else if (ev.state === 'done') {
        // 回合汇总卡：聚合本轮块 + 语音播报统一出口
        // Turn summary card: aggregate this turn's blocks + unified speech exit.
        const counts: Record<string, number> = {}
        for (const b of target) counts[b.type] = (counts[b.type] || 0) + 1
        target.push(makeBlock('summary', {
          status: ev.status,
          summary_text: ev.summary,
          tts_text: ev.summary,
          counts,
          block_ids: target.map(b => b.id),
        }))
      }
      break
    }
    case 'error': {
      target.push(makeBlock('notice', { level: 'error', text: ev.message }))
      break
    }
    case 'block': {
      // 离散块直通（image/file/ext:* 即插即用）
      const e = ev as BlockEvent
      if (e.block && typeof e.block === 'object') target.push(e.block as Block)
      break
    }
    case 'usage':
    case 'done':
      // usage 是会话级统计、done 是流控制，均不入块
      break
  }
}

/**
 * 关闭本条消息所有 streaming 块（回合收尾时调用）。
 * Close all streaming blocks of the message (called when the turn ends).
 *
 * @param target - 目标块列表。Target block list.
 */
export function finalizeBlocks(target: Block[]): void {
  for (const b of target) {
    if (b.meta?.streaming) b.meta.streaming = false
  }
}
