import { ref, type Ref } from 'vue'

/** 通知类型。Notification kind. */
export type ToastKind = 'ok' | 'err' | 'warn' | 'info'

/** 单条通知。A single notification entry. */
export interface ToastItem {
  /** 自增 id，用于 dismiss。Auto-increment id, used for dismiss. */
  id: number
  /** 通知类型（决定色调与存活时长）。Kind (drives tone and lifetime). */
  kind: ToastKind
  /** 通知文案。Notification text. */
  text: string
}

/** 各类型的存活时长（ms）；错误留更久以便阅读。Per-kind lifetime in ms; errors linger longer. */
const TTL: Record<ToastKind, number> = { ok: 3500, info: 3500, warn: 5000, err: 6000 }

/** 模块级单例队列：任意组件调用 notify 都会写进同一份列表。
 *  Module-level singleton queue: notify from any component writes into one list. */
const items = ref<ToastItem[]>([])
let seq = 0

/**
 * 立即移除指定通知。
 * Remove a notification immediately.
 *
 * @param id 通知 id。The notification id.
 */
function dismiss(id: number): void {
  items.value = items.value.filter((t) => t.id !== id)
}

/**
 * 入队一条通知并安排自动移除。
 * Enqueue a notification and schedule its auto-removal.
 *
 * @param kind 通知类型。Notification kind.
 * @param text 通知文案。Notification text.
 */
function push(kind: ToastKind, text: string): void {
  const id = ++seq
  items.value = [...items.value, { id, kind, text }]
  setTimeout(() => dismiss(id), TTL[kind])
}

/** 全局通知入口。Global notification entry point. */
export const notify = {
  /** 成功提示。Success notice. */
  ok: (text: string) => push('ok', text),
  /** 错误提示。Error notice. */
  err: (text: string) => push('err', text),
  /** 警告提示。Warning notice. */
  warn: (text: string) => push('warn', text),
  /** 普通信息。Informational notice. */
  info: (text: string) => push('info', text),
  /** 立即移除某条。Dismiss one entry. */
  dismiss,
  /** 清空全部（测试用）。Clear all (for tests). */
  clear: () => {
    items.value = []
  },
}

/**
 * 读取通知队列（供 UiToaster 渲染）。
 * Read the notification queue (rendered by UiToaster).
 *
 * @returns 通知列表。The notification list.
 */
export function useToast(): { items: Ref<ToastItem[]> } {
  return { items }
}
