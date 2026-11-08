// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/**
 * WebSocket 断线自动重连（docs/designs/10 4.5）。
 *
 * 后台空闲超时/网络抖动会断掉语音流；旧实现只把 handle 置空，用户必须关掉再打开
 * 语音才能恢复。现在非主动停止的断开走指数退避重连，代际号防止旧连接的回调覆盖
 * 新连接。
 *
 * Auto-reconnect on WebSocket drop (docs/designs/10 4.5). Idle timeouts / network
 * blips used to leave the user with a dead stream until they toggled voice off and
 * on; drops that were not user-initiated now retry with exponential backoff, and a
 * generation counter keeps stale callbacks from touching the new connection.
 */
class FakeWS {
  static instances: FakeWS[] = []
  static OPEN = 1
  readyState = 0
  onopen: (() => void) | null = null
  onmessage: ((ev: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  sent: string[] = []

  constructor(public url: string) {
    FakeWS.instances.push(this)
    // 让 start() 不用等外部事件：下一个微任务里连上并报 ready（构造返回后
    // onopen/onmessage 已赋值）。
    // Let start() complete without external driving: connect + ready on the next
    // microtask, after the constructor returns and the handlers are assigned.
    // 两级微任务：先 open，等 start() 接上 onmessage 之后再发 ready。
    // Two microtask hops: open first, then ready once start() has attached onmessage.
    void Promise.resolve()
      .then(() => { this.readyState = FakeWS.OPEN; this.onopen?.() })
      .then(() => { this.onmessage?.({ data: JSON.stringify({ type: 'ready' }) }) })
  }

  send(data: unknown) { this.sent.push(String(data)) }
  close() { this.readyState = 3 }
  /** 模拟服务端断开（非本地 stop）。Simulate a server-side drop (not a local stop). */
  drop() { this.readyState = 3; this.onclose?.() }
}

class FakeAudioContext {
  sampleRate = 16000
  destination = {}
  audioWorklet = { addModule: async () => {} }
  resume = async () => {}
  close = async () => {}
  createMediaStreamSource() { return { connect: () => {}, disconnect: () => {} } }
}

class FakeWorkletNode {
  port = { onmessage: null as null | ((ev: unknown) => void) }
  connect() {}
  disconnect() {}
}

function stubBrowser(): void {
  ;(window as any).AudioContext = FakeAudioContext
  ;(globalThis as any).AudioWorkletNode = FakeWorkletNode
  ;(globalThis as any).WebSocket = FakeWS
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: {
      getUserMedia: vi.fn(async () => ({ getTracks: () => [{ stop: vi.fn() }] })),
    },
  })
}

describe('createVoiceStream 断线重连', () => {
  beforeEach(() => {
    // 只假定时器：默认会连 queueMicrotask / nextTick 一起假，start() 的 Promise 链会卡住。
    // Fake timers only: the default set also fakes queueMicrotask / nextTick, which
    // stalls start()'s promise chain.
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    FakeWS.instances = []
    stubBrowser()
  })
  afterEach(() => { vi.useRealTimers() })

  it('服务端断开 → 指数退避后重建连接', async () => {
    const { createVoiceStream } = await import('../stream/streamClient')
    const closes: Array<{ willReconnect: boolean } | undefined> = []
    const handle = createVoiceStream({ onEvent: () => {}, onClose: (i) => closes.push(i) })
    await handle.start()
    expect(FakeWS.instances).toHaveLength(1)

    FakeWS.instances[0].drop()
    expect(closes.at(-1)?.willReconnect).toBe(true)

    await vi.advanceTimersByTimeAsync(600)
    expect(FakeWS.instances).toHaveLength(2)
  })

  it('主动 stop 不再重连', async () => {
    const { createVoiceStream } = await import('../stream/streamClient')
    const handle = createVoiceStream({ onEvent: () => {}, onClose: () => {} })
    await handle.start()
    handle.stop()
    await vi.advanceTimersByTimeAsync(5000)
    expect(FakeWS.instances).toHaveLength(1)
  })
})
