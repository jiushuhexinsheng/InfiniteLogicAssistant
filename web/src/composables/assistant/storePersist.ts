import { messages, tokenUsage, MAX_MESSAGES } from './store'
import type { ChatMessage } from './store'

/** 消息与 token 用量持久化的本地存储键。Local storage key for message and token usage persistence. */
const STORAGE_KEY = 'xluo.history'

/** 保存状态到本地存储。Save state to local storage. */
export function saveState() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      messages: messages.value.slice(-MAX_MESSAGES),
      tokenUsage: tokenUsage.value,
    }))
  } catch { /* 隐私模式/配额满：忽略。Privacy mode/quota full: ignore. */ }
}

/** 从本地存储加载状态。旧格式快照（消息无 blocks）直接丢弃 —— 已决定去掉旧历史。
 *  Load state from local storage. Old-format snapshots (messages without blocks)
 *  are dropped outright — old history is retired. */
export function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return
    const data = JSON.parse(raw)
    if (Array.isArray(data?.messages)) {
      const withBlocks = data.messages.filter(
        (m: any) => m && Array.isArray(m.blocks),
      ) as ChatMessage[]
      if (withBlocks.length) messages.value = withBlocks.slice(-MAX_MESSAGES)
    }
    if (data?.tokenUsage && typeof data.tokenUsage === 'object') tokenUsage.value = data.tokenUsage
  } catch { /* 解析失败忽略。Parse failure: ignore. */ }
}
