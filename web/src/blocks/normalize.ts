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
      const e = ev as AnswerEvent
      // 配对的 question 块标记已答（作答记录由 sendAnswer 以用户消息入流，
      // 这里不重复推块 —— 去重规则：问题在本流则只翻状态，不在才独立入块）。
      // Mark the paired question answered (the answer record enters as a user
      // message via sendAnswer; no duplicate block here — dedup rule: when the
      // question is in this stream, only flip its status; otherwise push standalone).
      const q = e.qid
        ? target.find(x => x.type === 'question' && x.payload.qid === e.qid)
        : undefined
      if (q) {
        q.payload.status = 'answered'
      } else {
        target.push(makeBlock('answer', {
          qid: e.qid,
          text: e.text,
          choice: e.choice ?? null,
          source: e.source || 'typed',
        }))
      }
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
