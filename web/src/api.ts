import type { ConfigResponse, PingResponse, TextResponse } from './types'
import { blobToWavBase64 } from './audio'

// ─── HTTP 封装 ───

const BASE = '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, options)
  if (!res.ok) {
    // 尝试解析 JSON 错误体，失败则用 HTTP 状态码
    let message = `HTTP ${res.status}`
    try {
      const err = await res.json()
      if (err?.error) message = err.error
    } catch { /* not JSON */ }
    throw new Error(message)
  }
  const data = await res.json()
  return data as T
}

async function get<T>(path: string): Promise<T> {
  return request<T>(path)
}

async function post<T>(path: string, data?: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: data ? JSON.stringify(data) : undefined,
  })
}

// ─── API 端点 ───

export const api = {
  ping: () => get<PingResponse>('/ping'),
  getConfig: () => get<ConfigResponse>('/config'),

  // 语音
  transcribe: async (blob: Blob): Promise<TextResponse> => {
    const base64Wav = await blobToWavBase64(blob)
    return post<TextResponse>('/voice/transcribe', { audio_base64: base64Wav })
  },
}
