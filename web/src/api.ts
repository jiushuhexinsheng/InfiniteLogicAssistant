import type { ConfigResponse, PingResponse, TextResponse, ToolCallResponse } from './types'
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

// ─── SSE 流式聊天 ───

export interface ChatHandlers {
  onContent: (text: string) => void
  onReasoning?: (text: string) => void
  onToolStart?: (name: string, args: Record<string, any>) => void
  onToolEnd?: (name: string, status: string, output: string) => void
  onDone: () => void
  onError: (msg: string) => void
  /** 用户主动中止（AbortController.abort()），区别于 onError */
  onAbort?: () => void
}

/** 消费 /api/ai/chat 的 SSE 事件流；signal 用于取消（对应前端"取消/停止"按钮） */
export async function streamChat(messages: unknown[], h: ChatHandlers, signal?: AbortSignal): Promise<void> {
  try {
    const resp = await fetch(`${BASE}/ai/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages }),
      signal,
    })
    if (!resp.ok || !resp.body) {
      let msg = `HTTP ${resp.status}`
      try {
        const e = await resp.json()
        if (e?.error) msg = e.error
      } catch { /* not JSON */ }
      throw new Error(msg)
    }
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      let idx: number
      while ((idx = buf.indexOf('\n\n')) !== -1) {
        const block = buf.slice(0, idx)
        buf = buf.slice(idx + 2)
        const line = block.split('\n').find(l => l.startsWith('data: '))
        if (!line) continue
        const data = line.slice(6).trim()
        if (data === '[DONE]') break
        let evt: any
        try { evt = JSON.parse(data) } catch { continue }
        switch (evt.type) {
          case 'content_delta': h.onContent(evt.text); break
          case 'reasoning_delta': h.onReasoning?.(evt.text); break
          case 'tool_start': h.onToolStart?.(evt.name, evt.args || {}); break
          case 'tool_end': h.onToolEnd?.(evt.name, evt.status, evt.output || ''); break
          case 'done': h.onDone(); return
          case 'error': h.onError(evt.message || '出错'); return
        }
      }
    }
    h.onDone()
  } catch (e: any) {
    if (e?.name === 'AbortError') {
      h.onAbort?.()
      return
    }
    h.onError(e?.message || String(e))
  }
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

  // 单工具执行（前端"重试失败工具"走后端真实重跑）
  callTool: async (name: string, args: Record<string, any>): Promise<ToolCallResponse> =>
    post<ToolCallResponse>('/tools/call', { name, args }),
}
