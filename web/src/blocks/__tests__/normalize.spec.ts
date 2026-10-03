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

  /** question/answer 配对（截图 bug #1 修复）：answer 贴到问题块**后一位**入块、
   *  翻已答态；choice 展示选项 label；同一 qid 重复事件幂等。
   *  此前 answer 只翻状态、记录由 sendAnswer 落独立用户气泡 —— 问答被卡片边界
   *  拆散、作答气泡还排在卡片后续事件之下（时序倒置）。
   *
   *  question/answer pairing (screenshot bug #1 fix): the answer enters as a block
   *  right AFTER its question, flipping the answered state; a choice displays the
   *  option label; duplicate events for the same qid are idempotent. Previously the
   *  answer only flipped status and the record went to a detached user bubble,
   *  splitting Q from A across the card boundary. */
  it('question/answer 配对：答案紧贴问题入块（修「问题和回答分离」）', () => {
    const blocks: Block[] = []
    applyEvent(ev({ type: 'question', question: '确认执行吗？', session_id: 's', kind: 'choice',
                    options: [{ value: 'yes', label: '确认' }], qid: 'q1' }), blocks)
    applyEvent(ev({ type: 'answer', qid: 'q1', choice: 'yes', source: 'button' }), blocks)
    expect(blocks).toHaveLength(2)
    expect(blocks[0].type).toBe('question')
    expect(blocks[0].payload.status).toBe('answered')
    expect(blocks[1].type).toBe('answer')
    expect(blocks[1].payload.qid).toBe('q1')
    expect(blocks[1].payload.text).toBe('确认')   // choice → 选项 label（非机器值）
    // 幂等：SSE 回声 / sendAnswer 本地入块谁先到，后者不再重复推
    // Idempotent: whichever of the SSE echo / sendAnswer local insert arrives second
    // does not push a duplicate.
    applyEvent(ev({ type: 'answer', qid: 'q1', text: '', choice: 'yes', source: 'button' }), blocks)
    expect(blocks).toHaveLength(2)
  })

  /** 文本作答：原文入块、紧贴问题。Text answer: verbatim, right after the question. */
  it('文本作答贴问题后，原文入块', () => {
    const blocks: Block[] = []
    applyEvent(ev({ type: 'question', question: '哪个城市？', session_id: 's', kind: 'text', options: [], qid: 'q1' }), blocks)
    applyEvent(ev({ type: 'answer', qid: 'q1', text: '上海', source: 'voice' }), blocks)
    expect(blocks).toHaveLength(2)
    expect(blocks[1].type).toBe('answer')
    expect(blocks[1].payload.text).toBe('上海')
    expect(blocks[1].payload.source).toBe('voice')
    expect(blocks[0].payload.status).toBe('answered')
  })

  /** timeout 作答只翻已答态（收起问题卡），无作答文本可展示 → 不入答案块。 */
  it('timeout 作答只翻态不入答案块', () => {
    const blocks: Block[] = []
    applyEvent(ev({ type: 'question', question: '确认执行吗？', session_id: 's', kind: 'choice',
                    options: [{ value: 'yes', label: '确认' }], qid: 'q1' }), blocks)
    applyEvent(ev({ type: 'answer', qid: 'q1', text: '', choice: 'no', source: 'timeout' }), blocks)
    expect(blocks).toHaveLength(1)
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

  /** 离散块分段（修「回答问题弹出的组件文字和布局错乱」）：question 入列即关闭
   *  此前流式的 text/thinking。后端在操作者作答后还会继续发 content_delta（confirm/
   *  clarify 解除阻塞 → executor 续跑发射），若倒灌进问题前的旧 text 块，续写文本
   *  会渲染到问题卡**上方**、问答被钉在消息末尾 —— 时序倒置。后续增量另起新块。
   *
   *  Discrete-block segmentation (fixes "the question popup's text and layout are
   *  scrambled"): a question entering the list closes the still-streaming text/
   *  thinking block. The backend keeps emitting content_delta after the operator
   *  answers (confirm/clarify unblock → executor resumes), and folding it into the
   *  pre-question text block renders the continuation ABOVE the question card with
   *  Q/A pinned to the end — time-inverted. Later deltas start a new block. */
  it('question 分段：作答后的续写另起文本块（不倒灌到问题上方）', () => {
    const blocks: Block[] = []
    applyEvent(ev({ type: 'content_delta', text: '我先检查磁盘' }), blocks)
    applyEvent(ev({ type: 'question', question: '要清理吗？', session_id: 's', kind: 'text', options: [], qid: 'q1' }), blocks)
    applyEvent(ev({ type: 'answer', qid: 'q1', text: '清理', source: 'typed' }), blocks)
    applyEvent(ev({ type: 'content_delta', text: '，已释放 3.2GB' }), blocks)
    expect(blocks.map(b => b.type)).toEqual(['text', 'question', 'answer', 'text'])
    expect(blocks[0].payload.md).toBe('我先检查磁盘')
    expect(blocks[0].meta?.streaming).toBe(false)   // question 入列即分段关闭
    expect(blocks[3].payload.md).toBe('，已释放 3.2GB')
    expect(blocks[3].meta?.streaming).toBe(true)
  })

  /** 同一规则适用于 tool_start：工具后的文本不再倒灌到工具上方。
   *  Same rule for tool_start: post-tool text no longer folds above the tool. */
  it('tool_start 分段：工具后的文本另起块', () => {
    const blocks: Block[] = []
    applyEvent(ev({ type: 'content_delta', text: '查一下' }), blocks)
    applyEvent(ev({ type: 'tool_start', name: 'weather', args: {}, call_id: 'c1' }), blocks)
    applyEvent(ev({ type: 'content_delta', text: '晴，25度' }), blocks)
    expect(blocks.map(b => b.type)).toEqual(['text', 'tool', 'text'])
    expect(blocks[0].payload.md).toBe('查一下')
    expect(blocks[2].payload.md).toBe('晴，25度')
  })
})
