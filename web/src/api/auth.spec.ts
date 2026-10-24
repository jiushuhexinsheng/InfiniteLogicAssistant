// @vitest-environment jsdom
/**
 * API Token 鉴权单元测试 —— 非 localhost 部署时服务端强制 X-API-Token。
 * API token auth tests — the server enforces X-API-Token on non-localhost deployments.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { authHeaders, getApiToken, setApiToken, withTokenParam } from './auth'
import { request } from './http'

const KEY = 'xluo.apiToken'

afterEach(() => {
  localStorage.removeItem(KEY)
  window.history.replaceState({}, '', '/')
  vi.unstubAllGlobals()
})

describe('API token', () => {
  it('未配置时不发送鉴权头', () => {
    expect(getApiToken()).toBe('')
    expect(authHeaders()).toEqual({})
  })

  it('设置后进入鉴权头', () => {
    setApiToken('tk-1')
    expect(getApiToken()).toBe('tk-1')
    expect(authHeaders()).toEqual({ 'X-API-Token': 'tk-1' })
  })

  it('URL ?token= 可引导一次并落盘，随后从地址栏移除', () => {
    window.history.replaceState({}, '', '/?token=boot-1')
    expect(getApiToken()).toBe('boot-1')
    expect(localStorage.getItem(KEY)).toBe('boot-1')
    expect(window.location.search).toBe('')
  })

  it('WebSocket URL 追加 token 查询参数', () => {
    setApiToken('tk 2')
    expect(withTokenParam('/api/voice/asr/stream')).toBe(
      '/api/voice/asr/stream?token=tk%202',
    )
    expect(withTokenParam('/api/x?a=1')).toBe('/api/x?a=1&token=tk%202')
  })

  it('request() 把 token 放进请求头', async () => {
    setApiToken('tk-3')
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true }),
    })
    vi.stubGlobal('fetch', mockFetch)
    await request('/ping')
    const init = mockFetch.mock.calls[0][1] as RequestInit
    expect(new Headers(init.headers).get('X-API-Token')).toBe('tk-3')
  })
})
