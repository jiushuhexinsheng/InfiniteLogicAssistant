import { describe, it, expect, vi, beforeEach } from 'vitest'

// node 测试环境无 window.AudioContext，blobToWavBase64 无法真正运行；mock 掉它（同 apiWake.spec.ts），
// 聚焦验证三端点路径与请求体。api.callStart/callSegment 内部闭包调用模块私有 post，导出的 post mock
// 拦不到内部调用，故按仓库既有做法桩掉全局 fetch，从请求侧断言。
// The node test env has no window.AudioContext, so blobToWavBase64 can't run; mock it (same as
// apiWake.spec.ts) and focus on the three endpoint paths + bodies. api.callStart/callSegment call the
// module-private post via closure, which an exported-post mock cannot intercept, so we stub global
// fetch (repo precedent) and assert from the request side.
vi.mock('../../../audio', () => ({ blobToWavBase64: vi.fn(async () => 'BASE64_WAV') }))

/** 通话 API 封装：三端点打到 /voice/call/*，segment 体带 wav base64 与焦点/窗口元数据。
 *  Call-mode API wrappers: three endpoints hit /voice/call/*; the segment body carries wav base64
 *  plus focus/window metadata. */
describe('通话 API 封装', () => {
  beforeEach(() => vi.clearAllMocks())

  it('callSegment 打包 wav 并带焦点/窗口元数据', async () => {
    const calls: { url: string; body?: string }[] = []
    vi.stubGlobal('fetch', vi.fn(async (url: string, init: any) => {
      calls.push({ url: String(url), body: init?.body })
      return { ok: true, status: 200, json: async () => ({ ok: true, hit: true, text: '打开记事本' }) }
    }))
    const { api } = await import('../../../api')
    const blob = new Blob([new Uint8Array([1, 2, 3])], { type: 'audio/wav' })
    const r = await api.callSegment(blob, { tabFocused: true, inOpenWindow: false })
    expect(r.hit).toBe(true)
    expect(calls[0].url).toContain('/voice/call/segment')
    const body = JSON.parse(String(calls[0].body))
    expect(body).toMatchObject({ tab_focused: true, in_open_window: false })
    expect(typeof (body as { audio_base64: string }).audio_base64).toBe('string')
    // 复用断言：wav 编码必须走 blobToWavBase64 helper，而不是另起一条转换路径。
    // Reuse assertion: the wav encoding must go through the blobToWavBase64 helper.
    expect((await import('../../../audio')).blobToWavBase64).toHaveBeenCalledWith(blob)
  })

  it('callStart/callStop 调对应端点', async () => {
    const urls: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      urls.push(String(url))
      return { ok: true, status: 200, json: async () => ({ ok: true }) }
    }))
    const { api } = await import('../../../api')
    await api.callStart()
    await api.callStop()
    expect(urls[0]).toContain('/voice/call/start')
    expect(urls[1]).toContain('/voice/call/stop')
  })
})
