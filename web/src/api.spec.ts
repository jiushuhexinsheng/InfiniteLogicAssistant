/**
 * API 模块单元测试
 * API Module Unit Tests
 */
import { describe, it, expect, vi } from 'vitest'
import { streamUtter } from './api'

/**
 * 创建模拟 SSE 流
 * Create mock SSE stream
 * @param events - SSE 事件数组 / SSE event array
 * @returns ReadableStream<Uint8Array> - 模拟的 SSE 流 / Mock SSE stream
 */
function sseStream(events: string[]): ReadableStream<Uint8Array> {
  const data = events.join('\n\n') + '\n\n'
  return new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(data))
      controller.close()
    },
  })
}

describe('streamUtter SSE', () => {
  // 测试解析事件并按序回调
  // Test parsing events and sequential callbacks
  it('解析事件并按序回调', async () => {
    // 模拟 fetch 响应 / Mock fetch response
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      body: sseStream([
        'data: {"type":"task_state","state":"understanding","session_id":"s1"}',
        'data: {"type":"content_delta","text":"你好"}',
        'data: {"type":"done","session_id":"s1"}',
      ]),
    })
    // 注入模拟的全局 fetch / Inject mock global fetch
    vi.stubGlobal('fetch', mockFetch)
    // 记录回调调用顺序 / Record callback call order
    const calls: string[] = []
    // 执行 streamUtter / Execute streamUtter
    const sid = await streamUtter('hi', {
      onTaskState: (s) => calls.push(`task:${s.state}`),
      onContent: (t) => calls.push(`text:${t}`),
      onDone: () => calls.push('done'),
    })
    // 验证 session_id / Verify session_id
    expect(sid).toBe('s1')
    // 验证回调顺序 / Verify callback order
    expect(calls).toEqual(['task:understanding', 'text:你好', 'done'])
    // 清理全局模拟 / Cleanup global mocks
    vi.unstubAllGlobals()
  })

  // 测试网络错误自动重试
  // Test network error auto-retry
  it('网络错误（未收到事件）自动重试一次', async () => {
    // 模拟第一次请求失败，第二次成功 / Mock first request fails, second succeeds
    let attempt = 0
    const mockFetch = vi.fn().mockImplementation(async () => {
      attempt++
      if (attempt === 1) throw new TypeError('Failed to fetch')
      return { ok: true, body: sseStream(['data: {"type":"done"}']) }
    })
    // 注入模拟的全局 fetch / Inject mock global fetch
    vi.stubGlobal('fetch', mockFetch)
    // 创建模拟回调 / Create mock callbacks
    const onError = vi.fn()
    const onDone = vi.fn()
    // 执行 streamUtter / Execute streamUtter
    await streamUtter('hi', { onError, onDone })
    // 验证 fetch 被调用 2 次 / Verify fetch called 2 times
    expect(mockFetch).toHaveBeenCalledTimes(2)
    // 验证 onDone 被调用 / Verify onDone called
    expect(onDone).toHaveBeenCalled()
    // 验证 onError 未被调用 / Verify onError not called
    expect(onError).not.toHaveBeenCalled()
    // 清理全局模拟 / Cleanup global mocks
    vi.unstubAllGlobals()
  })

  // 测试 HTTP 业务错误不重试
  // Test HTTP business error doesn't retry
  it('HTTP 业务错误不重试', async () => {
    // 模拟 HTTP 400 错误响应 / Mock HTTP 400 error response
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false, status: 400, json: async () => ({ error: 'bad request' }),
    })
    // 注入模拟的全局 fetch / Inject mock global fetch
    vi.stubGlobal('fetch', mockFetch)
    // 创建模拟错误回调 / Create mock error callback
    const onError = vi.fn()
    // 执行 streamUtter / Execute streamUtter
    await streamUtter('hi', { onError })
    // 验证 fetch 只被调用 1 次（不重试）/ Verify fetch called only 1 time (no retry)
    expect(mockFetch).toHaveBeenCalledTimes(1)
    // 验证 onError 被调用并传递错误信息 / Verify onError called with error message
    expect(onError).toHaveBeenCalledWith('bad request')
    // 清理全局模拟 / Cleanup global mocks
    vi.unstubAllGlobals()
  })

  // 选择类提问：kind 与 options 透传给 onQuestion
  // A choice question passes kind and options through to onQuestion
  it('question 事件的 kind 与 options 透传', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      body: sseStream([
        'data: {"type":"question","question":"确认执行吗？","session_id":"s1","kind":"choice","options":[{"value":"yes","label":"确认"},{"value":"no","label":"取消"}]}',
        'data: {"type":"done","session_id":"s1"}',
      ]),
    })
    vi.stubGlobal('fetch', mockFetch)
    const onQuestion = vi.fn()
    await streamUtter('hi', { onQuestion, onDone: vi.fn() })
    expect(onQuestion).toHaveBeenCalledWith({
      question: '确认执行吗？', session_id: 's1', kind: 'choice',
      options: [{ value: 'yes', label: '确认' }, { value: 'no', label: '取消' }],
    })
    // 清理全局模拟 / Cleanup global mocks
    vi.unstubAllGlobals()
  })
})

/**
 * 创建「先吐一个事件再抛错」的流，用于测试「流已开始后中断」分支。
 * Create a stream that emits one event then errors, for testing the
 * "interrupted after stream started" branch.
 *
 * 必须用 pull 分两次交付：default stream 上 controller.error() 会丢弃已入队的
 * chunk，若在 start 里 enqueue + error，首读就直接 reject，事件永远读不到。
 *
 * Must deliver across two pulls: on a default stream, controller.error() discards
 * queued chunks, so enqueue + error inside start makes the very first read reject
 * and the event is never observed.
 *
 * @param reason - 抛出的中断原因 / The error reason to reject with
 * @returns ReadableStream<Uint8Array> - 模拟流 / Mock stream
 */
function sseStreamThenFail(reason: unknown): ReadableStream<Uint8Array> {
  let sent = false
  return new ReadableStream({
    pull(controller) {
      if (!sent) {
        sent = true
        controller.enqueue(new TextEncoder().encode('data: {"type":"content_delta","text":"hi"}\n\n'))
        return
      }
      controller.error(reason)
    },
  })
}

describe('streamUtter 流中断错误文案', () => {
  // 已收到事件后中断（无 session_id 无法 resume）：给出固定恢复提示，且不盲目重试主连接。
  // Interrupted after events received (no session_id → cannot resume): a fixed recovery
  // notice, no blind main-connection retry.
  it('流已开始后中断且无会话标识 → 固定恢复文案、不重连主连接', async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, body: sseStreamThenFail(new Error('流读取失败')) })
    vi.stubGlobal('fetch', mockFetch)
    const onError = vi.fn()
    // 执行 streamUtter / Execute streamUtter
    await streamUtter('hi', { onError, onDone: vi.fn() })
    // 主连接只打一次（resume 因无 session 标识不发起）/ One main call (resume never starts without a session id)
    expect(mockFetch).toHaveBeenCalledTimes(1)
    // 文案不内嵌底层错误、不渲染 "null"（docs/designs/06 固定提示）。
    // The wording embeds neither the raw error nor a literal "null" (fixed notice, docs/designs/06).
    expect(onError).toHaveBeenCalledWith('连接中断且无会话标识，无法恢复')
    // 清理全局模拟 / Cleanup global mocks
    vi.unstubAllGlobals()
  })

  // 非 Error 的中断原因（如无参 reject）走同一条固定文案路径 —— 不会渲染 "null"。
  // A non-Error reason (e.g. reject() with no argument) takes the same fixed-notice
  // path — never rendering "null".
  it('非 Error 中断原因同样走固定文案（无 null 字面量）', async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, body: sseStreamThenFail(null) })
    vi.stubGlobal('fetch', mockFetch)
    const onError = vi.fn()
    // 执行 streamUtter / Execute streamUtter
    await streamUtter('hi', { onError, onDone: vi.fn() })
    // 验证文案 / Verify the message
    expect(onError).toHaveBeenCalledWith('连接中断且无会话标识，无法恢复')
    // 清理全局模拟 / Cleanup global mocks
    vi.unstubAllGlobals()
  })
})

/** 助手模式必须出现在 /voice/utter 请求体里 —— 这是前端模式开关与后端行为的接入点。
 *  The assistant mode must appear in the /voice/utter request body: the integration point
 *  between the frontend mode switch and the backend behaviour. */
describe('streamUtter 透传 mode', () => {
  it('opts.mode 进入请求体', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true, body: sseStream(['data: {"type":"done","session_id":"s1"}']),
    })
    vi.stubGlobal('fetch', mockFetch)
    await streamUtter('hi', { onDone: vi.fn() }, { mode: 'task' })
    const sent = JSON.parse(mockFetch.mock.calls[0][1].body)
    expect(sent.mode).toBe('task')
    vi.unstubAllGlobals()
  })

  it('未传 mode 时请求体不带该字段（后端缺省 chat）', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true, body: sseStream(['data: {"type":"done","session_id":"s1"}']),
    })
    vi.stubGlobal('fetch', mockFetch)
    await streamUtter('hi', { onDone: vi.fn() })
    const sent = JSON.parse(mockFetch.mock.calls[0][1].body)
    expect(sent.mode).toBeUndefined()
    vi.unstubAllGlobals()
  })
})

/** 断线恢复（docs/designs/06）：seq 去重、ping 不分发、resume 接管收束、404 兜底。
 *  Disconnect resume (docs/designs/06): seq dedup, ping not dispatched, resume takes
 *  over to completion, 404 fallback. */
describe('streamUtter 断线恢复', () => {
  /** 主连接：吐一帧后网络中断。Main connection: one frame then a network error. */
  function mainStreamThenFail(): ReadableStream<Uint8Array> {
    let sent = false
    return new ReadableStream({
      pull(controller) {
        if (!sent) {
          sent = true
          controller.enqueue(new TextEncoder().encode(
            'data: {"type":"task_state","state":"understanding","session_id":"s1","seq":1}\n\n'))
          return
        }
        controller.error(new Error('网络断了'))
      },
    })
  }

  it('断线后 resume：重复 seq 被跳过、done 正常收束', async () => {
    const resumeBody = sseStream([
      'data: {"type":"content_delta","text":"A","seq":2}',
      'data: {"type":"content_delta","text":"A","seq":2}',   // 回放重复帧（应被跳过）。Replay duplicate (must be dropped).
      'data: {"type":"content_delta","text":"B","seq":3}',
      'data: {"type":"done","session_id":"s1","seq":4}',
    ])
    const mockFetch = vi.fn()
      .mockResolvedValueOnce({ ok: true, body: mainStreamThenFail() })
      .mockResolvedValueOnce({ ok: true, body: resumeBody })
    vi.stubGlobal('fetch', mockFetch)

    const seqs: number[] = []
    const texts: string[] = []
    const onDone = vi.fn()
    await streamUtter('hi', {
      onEvent: (e: any) => { if (typeof e.seq === 'number') seqs.push(e.seq) },
      onContent: (t: string) => texts.push(t),
      onDone,
    })

    expect(mockFetch).toHaveBeenCalledTimes(2)
    const resumeReq = JSON.parse(mockFetch.mock.calls[1][1].body)
    expect(mockFetch.mock.calls[1][0]).toContain('/voice/resume')
    expect(resumeReq).toEqual({ session_id: 's1', last_seq: 1 })
    expect(seqs).toEqual([1, 2, 3, 4])      // 重复的 seq2 只出现一次。The duplicate seq2 appears once.
    expect(texts).toEqual(['A', 'B'])
    expect(onDone).toHaveBeenCalledTimes(1)
    vi.unstubAllGlobals()
  })

  it('ping 帧不进分发也不占 seq', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true, body: sseStream([
        'data: {"type":"ping"}',
        'data: {"type":"content_delta","text":"你好","seq":1}',
        'data: {"type":"done","seq":2}',
      ]),
    })
    vi.stubGlobal('fetch', mockFetch)
    const events: any[] = []
    await streamUtter('hi', { onEvent: (e: any) => events.push(e), onDone: vi.fn() })
    expect(events.map(e => e.type)).toEqual(['content_delta', 'done'])
    vi.unstubAllGlobals()
  })

  it('resume 404 → 固定兜底文案（历史重载提示）', async () => {
    const mockFetch = vi.fn()
      .mockResolvedValueOnce({ ok: true, body: mainStreamThenFail() })
      .mockResolvedValueOnce({
        ok: false, status: 404,
        json: async () => ({ error: 'no_run' }),
      })
    vi.stubGlobal('fetch', mockFetch)
    const onError = vi.fn()
    await streamUtter('hi', { onEvent: vi.fn(), onError, onDone: vi.fn() })
    expect(onError).toHaveBeenCalledWith('连接中断，回合已结束：请刷新历史查看')
    vi.unstubAllGlobals()
  })
})
