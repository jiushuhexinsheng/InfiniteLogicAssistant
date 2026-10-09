import { api } from '../../api'
import { formatError } from '../../errors'
import { state, messages, tokenUsage, pendingQuestion, currentSessionId, addMessage } from './store'
import { makeBlock } from '../../blocks/normalize'
import { runTurn } from './useChat'

// ── 会话分叉 / 编辑重发 / 重新生成（docs/designs/07）──
// 约束：整段覆盖式存储下，改写历史必须先分叉（源会话在服务端只读不动）；
// 回合进行中一律禁用（与排队机制的「显式动作」边界一致）。

/** 是否处于可做分叉/编辑动作的空闲态。Whether we are idle enough for fork/edit actions. */
function idleForEdit(): boolean {
  return state.value === 'done' || state.value === 'error' || state.value === 'idle'
}

/** 从 index 处（含该条）分叉：服务端复制前缀为新会话，本地截断并切到新 id。
 *  前缀内容本地与服务端一致，省一次历史拉取。失败返回 false。
 *
 *  Fork at index (inclusive): the server copies the prefix into a new conversation;
 *  locally truncate and switch to the new id. The prefix is identical on both sides,
 *  so no history refetch is needed. Returns false on failure.
 *
 *  @param index - 分叉边界消息下标（含）。Fork boundary message index (inclusive). */
export async function forkAt(index: number): Promise<boolean> {
  if (!idleForEdit()) return false
  const sid = currentSessionId.value
  if (!sid || index < 0 || index >= messages.value.length) return false
  try {
    const r = await api.forkSession(sid, index)
    if (!r.ok) return false
    const prefix = messages.value.slice(0, index + 1)
    currentSessionId.value = r.session.id
    messages.value = prefix
    pendingQuestion.value = null
    tokenUsage.value = {}
    return true
  } catch (e) {
    addMessage('system', '分叉失败：' + formatError(e))
    return false
  }
}

/** 编辑 index 处的用户消息并重发：非末条先分叉（保原路径），改写后起新一轮。
 *
 *  Edit the user message at index and resend: non-tail messages fork first (the
 *  original path is kept); rewrite then start a new turn.
 *
 *  @param index - 被编辑消息下标。Index of the edited message.
 *  @param newText - 新文本。The new text.
 *  @returns 是否成功。Whether it succeeded. */
export async function sendEdited(index: number, newText: string): Promise<boolean> {
  const t = newText.trim()
  if (!t || !idleForEdit()) return false
  const target = messages.value[index]
  if (!target || target.role !== 'user') return false
  if (index < messages.value.length - 1) {
    const ok = await forkAt(index)     // 保原路径（编辑必须先分叉）。Keep the original path.
    if (!ok) return false
  } else {
    messages.value.splice(index + 1)   // 末条编辑：防御性截尾。Tail edit: defensive trim.
  }
  const m = messages.value[index]
  m.text = t
  m.blocks = [makeBlock('text', { md: t, variant: 'bubble' })]
  void runTurn()
  return true
}

/** 重新生成 index 处的助手回复：分叉到其前一条用户消息（含），用原话重跑一轮。
 *
 *  Regenerate the assistant reply at index: fork to the user message before it
 *  (inclusive) and rerun that turn with the original words.
 *
 *  @param index - 被重新生成的助手消息下标。Index of the assistant message.
 *  @returns 是否成功。Whether it succeeded. */
export async function regenerate(index: number): Promise<boolean> {
  if (!idleForEdit()) return false
  const m = messages.value[index]
  if (!m || m.role !== 'assistant') return false
  let u = -1
  for (let i = index - 1; i >= 0; i--) {
    if (messages.value[i].role === 'user') { u = i; break }
  }
  if (u < 0) return false
  const ok = await forkAt(u)           // 前缀含原问题、去掉本条回复。Prefix keeps the question, drops this reply.
  if (!ok) return false
  void runTurn()                        // 末条是用户消息 → 直接重跑。Last message is the user's → rerun.
  return true
}
