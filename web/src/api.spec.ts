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
  // 已收到事件后中断：文案走统一格式化，且不重试
  // Interrupted after events received: message uses the unified formatter, no retry
  it('流已开始后中断时 onError 收到统一格式的文案', async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, body: sseStreamThenFail(new Error('流读取失败')) })
    vi.stubGlobal('fetch', mockFetch)
    const onError = vi.fn()
    // 执行 streamUtter / Execute streamUtter
    await streamUtter('hi', { onError, onDone: vi.fn() })
    // 已开始后中断不重试 / No retry after the stream has started
    expect(mockFetch).toHaveBeenCalledTimes(1)
    // 全角冒号 + formatError 文案 / Full-width colon + formatError message
    expect(onError).toHaveBeenCalledWith('连接中断：流读取失败')
    // 清理全局模拟 / Cleanup global mocks
    vi.unstubAllGlobals()
  })

  // 非 Error 的中断原因（如无参 reject）不应渲染成 "null" 字面量
  // A non-Error reason (e.g. reject() with no argument) must not render as the literal "null"
  it('非 Error 中断原因回退为「未知错误」而非 null 字面量', async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, body: sseStreamThenFail(null) })
    vi.stubGlobal('fetch', mockFetch)
    const onError = vi.fn()
    // 执行 streamUtter / Execute streamUtter
    await streamUtter('hi', { onError, onDone: vi.fn() })
    // 验证文案 / Verify the message
    expect(onError).toHaveBeenCalledWith('连接中断：未知错误')
    // 清理全局模拟 / Cleanup global mocks
    vi.unstubAllGlobals()
  })
})
