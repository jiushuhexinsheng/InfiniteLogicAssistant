import { describe, it, expect, vi, beforeEach } from 'vitest'

// node 测试环境无 window.AudioContext，blobToWavBase64 无法真正运行；mock 掉它，
// 聚焦验证客户端走 /voice/wake 且 body 携带 audio_base64（复用该 helper 本身由 transcribe 路径保证）。
// The node test environment has no window.AudioContext, so blobToWavBase64 can't actually run; mock it
// and focus on asserting the client hits /voice/wake with an audio_base64 body (reuse of the helper is
// already guaranteed by the shared transcribe path).
vi.mock('../../../audio', () => ({ blobToWavBase64: vi.fn(async () => 'BASE64_WAV') }))

/** 唤醒检测客户端：必须复用 transcribe 的「Blob → WAV base64」转换，且带超时。
 *  The wake-detect client must reuse transcribe's Blob → WAV base64 conversion and carry a timeout. */
describe('api.wakeDetect', () => {
  beforeEach(() => { vi.resetModules(); vi.restoreAllMocks() })

  /** 走 /voice/wake 端点，body 里是 wav base64。
   *  It posts to /voice/wake with a wav base64 body. */
  it('POST /voice/wake 带 audio_base64', async () => {
    const calls: any[] = []
    vi.stubGlobal('fetch', vi.fn(async (url: string, init: any) => {
      calls.push({ url, body: init?.body })
      return { ok: true, status: 200, json: async () => ({ ok: true, matched: true, command: '查天气', text: '衍衡，查天气。' }) }
    }))
    const { api } = await import('../../../api')
    const r = await api.wakeDetect(new Blob(['x']))
    expect(String(calls[0].url)).toContain('/voice/wake')
    expect(JSON.parse(String(calls[0].body)).audio_base64).toBeTruthy()
    expect(r.matched).toBe(true)
    expect(r.command).toBe('查天气')
  })
})
