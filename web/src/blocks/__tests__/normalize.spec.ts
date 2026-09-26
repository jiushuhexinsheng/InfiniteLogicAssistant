import { describe, expect, it } from 'vitest'
import { applyEvent, finalizeBlocks, makeBlock } from '../normalize'
import type { Block } from '../types'
import type { SseEvent } from '../../types'

/** 事件 → 块流 reducer：全部 SSE 事件的块变更规则。
 *  Event → block-stream reducer: all SSE event mutation rules. */
describe('normalize 事件归一', () => {
  const ev = (e: any) => e as SseEvent

  /** content_delta 合并进 streaming text 块。content_delta merges into a streaming text block. */
  it('content_delta 增量合并进 text 块', () => {
    const blocks: Block[] = []
    applyEvent(ev({ type: 'content_delta', text: '你好' }), blocks)
    applyEvent(ev({ type: 'content_delta', text: '，世界' }), blocks)
    expect(blocks).toHaveLength(1)
    expect(blocks[0].type).toBe('text')
    expect(blocks[0].payload.md).toBe('你好，世界')
    expect(blocks[0].meta?.streaming).toBe(true)
  })

  /** reasoning_delta 进 thinking 块（思考断链修复的前端侧）。
   *  reasoning_delta lands in a thinking block (frontend side of the thinking-chain fix). */
  it('reasoning_delta 归一进 thinking 块', () => {
    const blocks: Block[] = []
    applyEvent(ev({ type: 'reasoning_delta', text: '先想' }), blocks)
    applyEvent(ev({ type: 'reasoning_delta', text: '后算' }), blocks)
    expect(blocks).toHaveLength(1)
    expect(blocks[0].type).toBe('thinking')
    expect(blocks[0].payload.text).toBe('先想后算')
  })

  /** tool_start/tool_end 按 call_id 配对更新状态。
   *  tool_start/tool_end pair by call_id. */
  it('工具事件按 call_id 配对', () => {
    const blocks: Block[] = []
    applyEvent(ev({ type: 'tool_start', name: 'run_shell_tool', args: { c: 'ls' }, call_id: 'c1', agent: 'sub:doer' }), blocks)
    applyEvent(ev({ type: 'tool_end', name: 'run_shell_tool', status: 'ok', output: 'ok', call_id: 'c1', truncated: true, output_len: 900 }), blocks)
    expect(blocks).toHaveLength(1)
    const b = blocks[0]
    expect(b.type).toBe('tool')
    expect(b.agent).toBe('sub:doer')
    expect(b.payload.call_id).toBe('c1')
    expect(b.payload.status).toBe('ok')
    expect(b.payload.truncated).toBe(true)
    expect(b.payload.full_len).toBe(900)
  })

  /** question/answer 配对：问题在本流时 answer 只翻已答态（作答记录由 sendAnswer
   *  以用户消息入流，不重复推块）；问题不在本流时 answer 独立入块。
   *  question/answer pair: when the question is in this stream the answer only flips
   *  its status (the answer record enters as a user message via sendAnswer, no
   *  duplicate block); otherwise the answer enters as a standalone block. */
  it('question/answer 配对（问题在本流只翻状态）', () => {
    const blocks: Block[] = []
    applyEvent(ev({ type: 'question', question: '哪个城市？', session_id: 's', kind: 'text', options: [], qid: 'q1' }), blocks)
    applyEvent(ev({ type: 'answer', qid: 'q1', text: '上海', source: 'voice' }), blocks)
    expect(blocks).toHaveLength(1)  // 不重复推块
    expect(blocks[0].type).toBe('question')
    expect(blocks[0].payload.status).toBe('answered')
  })

  /** answer 事件无配对问题时独立入块（语音可审计）。A standalone answer block without a paired question. */
  it('answer 无配对问题时独立入块', () => {
    const blocks: Block[] = []
    applyEvent(ev({ type: 'answer', qid: 'q-x', text: '上海', source: 'voice' }), blocks)
    expect(blocks).toHaveLength(1)
    expect(blocks[0].type).toBe('answer')
    expect(blocks[0].payload.source).toBe('voice')
  })

  /** task_state done → summary 块（回合汇总卡，语音统一出口）。
   *  task_state done → summary block (turn card, unified speech exit). */
  it('task_state done 产生 summary 块', () => {
    const blocks: Block[] = [
      makeBlock('text', { md: 'x' }),
      makeBlock('tool', { name: 't', output: 'o' }),
    ]
    applyEvent(ev({ type: 'task_state', state: 'done', status: 'done', summary: '已查天气' }), blocks)
    const s = blocks.find(b => b.type === 'summary')
    expect(s?.payload.summary_text).toBe('已查天气')
    expect(s?.payload.tts_text).toBe('已查天气')
    expect(s?.payload.counts?.text).toBe(1)
    expect(s?.payload.block_ids).toHaveLength(2)
  })

  /** block 事件直通（image/file/ext 即插即用）。block event passes through. */
  it('block 事件直通离散块', () => {
    const blocks: Block[] = []
    const blk = makeBlock('ext:chart', { kind: 'bar' })
    applyEvent(ev({ type: 'block', block: blk }), blocks)
    expect(blocks).toHaveLength(1)
    expect(blocks[0].type).toBe('ext:chart')
  })

  /** usage/done 不入块（会话级统计与流控制）。
   *  usage/done never become blocks. */
  it('usage/done 不入块', () => {
    const blocks: Block[] = []
    applyEvent(ev({ type: 'usage', usage: {} }), blocks)
    applyEvent(ev({ type: 'done' }), blocks)
    expect(blocks).toHaveLength(0)
  })

  /** finalizeBlocks 关闭 streaming 标记。finalizeBlocks closes the streaming flag. */
  it('finalizeBlocks 关闭流式标记', () => {
    const blocks: Block[] = []
    applyEvent(ev({ type: 'content_delta', text: 'x' }), blocks)
    finalizeBlocks(blocks)
    expect(blocks[0].meta?.streaming).toBe(false)
  })
})
