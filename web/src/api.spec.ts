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
})
