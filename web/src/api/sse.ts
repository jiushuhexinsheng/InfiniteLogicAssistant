// （streamUtter 断线文案已改为 resume 流程的固定提示，docs/designs/06 —— 不再内嵌底层错误。）
// (streamUtter's disconnect wording is now a fixed resume-flow notice,
// docs/designs/06 — the underlying error is no longer embedded.)

import type { QuestionEvent, QuestionOption, SseEvent, TaskState, TokenUsage } from '../types'
import { BASE } from './http'

// ─── 编排 SSE：/api/voice/utter（唯一 agent 路径，含澄清/确认 question 事件）───
// ─── Orchestration SSE: /api/voice/utter (sole agent path, includes clarification/confirmation question events) ───

/**
 * Utter SSE 事件处理器接口
 * Utter SSE event handler interface
 */
export interface UtterHandlers {
  /** 原始事件通配回调（块 reducer 用，先于具体分发回调触发）。
   *  Wildcard raw-event callback (for the block reducer; fires before the specific handlers). */
  onEvent?: (ev: SseEvent) => void
  /** 任务状态变化回调。Task state change callback. */
  onTaskState?: (s: TaskState) => void
  /** 内容增量回调。Content delta callback. */
  onContent?: (text: string) => void
  /** 推理过程增量回调。Reasoning delta callback. */
  onReasoning?: (text: string) => void
  /** 工具开始执行回调。Tool start callback. */
  onToolStart?: (name: string, args: Record<string, any>) => void
  /** 工具执行结束回调。Tool end callback. */
  onToolEnd?: (name: string, status: string, output: string) => void
  /** Token 使用量回调。Token usage callback. */
  onUsage?: (usage: TokenUsage) => void
  /** 问题事件回调（澄清/确认）。Question event callback (clarification/confirmation). */
  onQuestion?: (q: { question: string; session_id: string; kind: QuestionEvent['kind']; options: QuestionOption[]; qid?: string }) => void
  /** 错误回调。Error callback. */
  onError?: (msg: string) => void
  /** 完成回调。Done callback. */
  onDone?: (sessionId: string) => void
  /** 用户主动中止（AbortController.abort()），区别于 onError */
  /** User initiated abort (AbortController.abort()), distinct from onError */
  onAbort?: () => void
}

/**
 * 消费 /api/voice/utter 的 SSE 事件流；返回 session_id（供 answer/stop 用）。
 * Consume SSE event stream from /api/voice/utter; returns session_id (for answer/stop use).
 * messages 为多轮历史种子（含当前用户消息）；signal 用于取消（对应"取消/停止"按钮）。
 * messages is multi-turn history seed (including current user message); signal is used for cancellation (corresponds to "cancel/stop" button).
 * 网络错误且未收到任何事件时自动重试一次；HTTP/业务错误与流中段不重试。
 * Auto-retry once on network error without any events received; no retry on HTTP/business errors or mid-stream interruption.
 * @param text - 用户输入文本 / User input text
 * @param h - 事件处理器 / Event handlers
 * @param opts - 可选参数 / Optional parameters
 * @returns Promise<string> - session_id
 */
export async function streamUtter(
  text: string,
  h: UtterHandlers,
  opts?: { messages?: { role: string; content: string }[]; signal?: AbortSignal; sessionId?: string; mode?: string },
): Promise<string> {
  let sessionId = ''
  const body: Record<string, unknown> = { text }
  if (opts?.messages?.length) body.messages = opts.messages
  if (opts?.sessionId) body.session_id = opts.sessionId
  // 助手模式随请求下发（后端据此决定完成后是否询问并存档）。
  // The assistant mode travels with the request (the backend uses it to decide whether to
  // ask and archive on completion).
  if (opts?.mode) body.mode = opts.mode

  // ── seq 游标与断线恢复（docs/designs/06）──
  // lastSeq：已消费的最大事件序号（服务端回放 seq≤lastSeq 的帧会被跳过 —— 重连不重复）。
  // Last consumed event seq (frames replayed with seq ≤ lastSeq are skipped — no
  // duplicates across reconnects).
  let lastSeq = 0
  let everReceived = false
  const MAX_RETRY = 1          // 主连接零事件重试（旧语义保留）。Main-conn zero-event retry (legacy).
  const RESUME_RETRY = 2       // resume 重试次数（退避 1s/3s）。Resume attempts (backoff 1s/3s).
  const PING_TIMEOUT_MS = 35000 // 35s 无任何帧（含 ping）判死。No frame (incl. ping) for 35s = dead.
  const sleep = (ms: number) => new Promise<void>(r => setTimeout(r, ms))

  /** 消费一条连接：分发事件（seq 去重 + ping 看门狗），返回结局。
   *  'closed' = 正常/业务错误/中止（收工）；'network' = 连接断了（可 resume）。
   *
   *  Consume one connection: dispatch events (seq dedup + ping watchdog) and return
   *  the outcome — 'closed' = normal/business error/abort (finished); 'network' =
   *  connection lost (resumable). */
  const consume = async (resp: Response): Promise<'closed' | 'network'> => {
    const reader = resp.body!.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    let timedOut = false
    let finished = false
    try {
      while (true) {
        // 看门狗：超时 cancel 读取器 → read() 立刻返回 → 按断线处理。
        // Watchdog: cancel the reader on timeout → read() returns at once → network loss.
        const timer = setTimeout(() => {
          timedOut = true
          try { void reader.cancel() } catch { /* ignore */ }
        }, PING_TIMEOUT_MS)
        let chunk: ReadableStreamReadResult<Uint8Array>
        try {
          chunk = await reader.read()
        } finally {
          clearTimeout(timer)
        }
        if (chunk.done) break
        buf += decoder.decode(chunk.value, { stream: true })
        let idx: number
        while ((idx = buf.indexOf('\n\n')) !== -1) {
          const block = buf.slice(0, idx)
          buf = buf.slice(idx + 2)
          const line = block.split('\n').find(l => l.startsWith('data: '))
          if (!line) continue
          const data = line.slice(6).trim()
          if (data === '[DONE]') continue
          let evt: any
          try { evt = JSON.parse(data) } catch { continue }
          // 心跳：只重置看门狗，不进分发、无 seq（docs/designs/06）。
          // Heartbeat: resets the watchdog only — not dispatched, carries no seq.
          if (evt.type === 'ping') continue
          // 回放去重：seq 在游标内（重连重发的旧帧）直接丢。
          // Replay dedup: a seq behind the cursor (an old frame resent on reconnect) is dropped.
          if (typeof evt.seq === 'number') {
            if (evt.seq <= lastSeq) continue
            lastSeq = evt.seq
          }
          everReceived = true
          // 原始事件先交通配回调（块 reducer 归一），再走具体分发
          // Raw events go to the wildcard callback (block reducer) first, then the specific dispatch
          h.onEvent?.(evt)
          switch (evt.type) {
            case 'task_state':
              if (evt.session_id) sessionId = evt.session_id
              h.onTaskState?.(evt)
              break
            case 'content_delta': h.onContent?.(evt.text); break
            case 'reasoning_delta': h.onReasoning?.(evt.text); break
            case 'tool_start': h.onToolStart?.(evt.name, evt.args || {}); break
            case 'tool_end': h.onToolEnd?.(evt.name, evt.status, evt.output || ''); break
            case 'usage': h.onUsage?.(evt.usage); break
            case 'question':
              if (evt.session_id) sessionId = evt.session_id
              h.onQuestion?.({ question: evt.question, session_id: evt.session_id, kind: evt.kind, options: evt.options, qid: evt.qid })
              break
            case 'error': h.onError?.(evt.message); finished = true; return 'closed'
            case 'done': h.onDone?.(sessionId); finished = true; return 'closed'
          }
        }
      }
      if (timedOut) return 'network'   // 看门狗杀读 → 断线。Watchdog killed the read → network loss.
      if (!finished) h.onDone?.(sessionId)  // 服务端正常收流但没发 done（防御）。Stream ended without done (defensive).
      return 'closed'
    } catch (e: any) {
      if (e?.name === 'AbortError') { h.onAbort?.(); return 'closed' }
      if (timedOut) return 'network'
      return 'network'
    }
  }

  /** 打开一条连接：utter（首连/零事件重试）或 resume。Open one connection. */
  const open = async (mode: 'main' | 'resume'): Promise<Response> => {
    if (mode === 'main') {
      return fetch(`${BASE}/voice/utter`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: opts?.signal,
      })
    }
    return fetch(`${BASE}/voice/resume`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId || opts?.sessionId || '', last_seq: lastSeq }),
      signal: opts?.signal,
    })
  }

  let mainTry = 0
  let resumeTry = 0
  let mode: 'main' | 'resume' = 'main'
  // 重连退避：第 1 次 1s、第 2 次 3s（docs/designs/06 §批2）。
  const RESUME_BACKOFF = [1000, 3000]
  for (;;) {
    let resp: Response
    try {
      resp = await open(mode)
    } catch (e: any) {
      if (e?.name === 'AbortError') { h.onAbort?.(); return sessionId }
      if (mode === 'main' && !everReceived && mainTry < MAX_RETRY) { mainTry++; continue }
      if (mode === 'resume' && resumeTry < RESUME_RETRY) {
        await sleep(RESUME_BACKOFF[Math.min(resumeTry, RESUME_BACKOFF.length - 1)])
        resumeTry++
        continue
      }
      h.onError?.(mode === 'main' ? '网络连接失败，请重试' : '连接中断：任务已在服务端继续，稍后刷新历史查看')
      return sessionId
    }
    if (!resp.ok || !resp.body) {
      let msg = `HTTP ${resp.status}`
      try {
        const e = await resp.json()
        if (e?.error) msg = e.error
      } catch { /* not JSON */ }
      if (mode === 'main' && resp.status !== 200) { h.onError?.(msg); return sessionId }
      if (mode === 'resume') {
        // 404 no_run = 运行已结束/不存在 → 历史重载兜底（调用方刷新）。
        if (resp.status === 404) { h.onError?.('连接中断，回合已结束：请刷新历史查看'); return sessionId }
        if (resumeTry < RESUME_RETRY) { await sleep(RESUME_BACKOFF[Math.min(resumeTry, 2 - 1)]); resumeTry++; mode = 'resume'; continue }
        h.onError?.(msg); return sessionId
      }
      h.onError?.(msg)
      return sessionId
    }
    const outcome = await consume(resp)
    if (outcome === 'closed') return sessionId
    // 断线（网络错/看门狗）→ 进入 resume（服务端宽限期内任务仍在跑）。
    // Network loss → resume (the server keeps the task alive inside its grace window).
    if (opts?.signal?.aborted) { h.onAbort?.(); return sessionId }
    mode = 'resume'
    resumeTry = 0
    if (!sessionId && !opts?.sessionId) { h.onError?.('连接中断且无会话标识，无法恢复'); return sessionId }
    await sleep(RESUME_BACKOFF[0])
    resumeTry = 1   // 首次重连已消费掉 1s 退避额度。The first reconnect spends the 1s slot.
  }
}
