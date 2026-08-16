import { describe, it, expect, vi } from 'vitest'
import { streamUtter } from './api'

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
  it('解析事件并按序回调', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      body: sseStream([
        'data: {"type":"task_state","state":"understanding","session_id":"s1"}',
        'data: {"type":"content_delta","text":"你好"}',
        'data: {"type":"done","session_id":"s1"}',
      ]),
    })
    vi.stubGlobal('fetch', mockFetch)
    const calls: string[] = []
    const sid = await streamUtter('hi', {
      onTaskState: (s) => calls.push(`task:${s.state}`),
      onContent: (t) => calls.push(`text:${t}`),
      onDone: () => calls.push('done'),
    })
    expect(sid).toBe('s1')
    expect(calls).toEqual(['task:understanding', 'text:你好', 'done'])
    vi.unstubAllGlobals()
  })

  it('网络错误（未收到事件）自动重试一次', async () => {
    let attempt = 0
    const mockFetch = vi.fn().mockImplementation(async () => {
      attempt++
      if (attempt === 1) throw new TypeError('Failed to fetch')
      return { ok: true, body: sseStream(['data: {"type":"done"}']) }
    })
    vi.stubGlobal('fetch', mockFetch)
    const onError = vi.fn()
    const onDone = vi.fn()
    await streamUtter('hi', { onError, onDone })
    expect(mockFetch).toHaveBeenCalledTimes(2)
    expect(onDone).toHaveBeenCalled()
    expect(onError).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
  })

  it('HTTP 业务错误不重试', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false, status: 400, json: async () => ({ error: 'bad request' }),
    })
    vi.stubGlobal('fetch', mockFetch)
    const onError = vi.fn()
    await streamUtter('hi', { onError })
    expect(mockFetch).toHaveBeenCalledTimes(1)
    expect(onError).toHaveBeenCalledWith('bad request')
    vi.unstubAllGlobals()
  })
})
