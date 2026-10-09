import { ref } from 'vue'
import { addMessage } from './store'
import { runTurn } from './useChat'

/** 待发消息队列：回合进行中用户再发 → 入队，回合收束自动连发（Open WebUI 式消息队列）。
 *  Outbox: sending while a turn runs queues the message; turn end flushes it
 *  (the Open WebUI-style message queue). */
const outbox: string[] = []

/** 队列长度（响应式，供输入框「排队中」徽标）。Queue length (reactive, for the input's
 *  "queued" badge). */
export const outboxCount = ref(0)

/** 取消词：立即中止并清队（排队不得吞掉取消）。Cancellation words: abort at once and
 *  clear the queue (the queue must never swallow a cancel). */
export const CANCEL_RE = /^(停止|取消|暂停|算了|别跑了|stop|cancel)$/i

export function enqueue(t: string) {
  outbox.push(t)
  outboxCount.value = outbox.length
}

export function clearOutbox() {
  outbox.length = 0
  outboxCount.value = 0
}

/** 回合收束后弹出下一条排队消息（链条式：每回合收束弹一条）。
 *  Pop the next queued message after a turn wraps up (chained: one per turn end). */
export function flushOutbox() {
  const t = outbox.shift()
  outboxCount.value = outbox.length
  if (!t) return
  addMessage('user', t)
  void runTurn()
}

/** 清空排队消息（输入框徽标点击）。Clear queued messages (input badge click). */
export function clearQueued() {
  clearOutbox()
}
