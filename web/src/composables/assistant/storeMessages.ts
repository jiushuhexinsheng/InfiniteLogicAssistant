import type { Block } from '../../blocks/types'
import { makeBlock } from '../../blocks/normalize'
import {
  state, messages, tokenUsage, partialText, statusLine, expanded,
  pendingQuestion, currentSessionId, MAX_MESSAGES,
} from './store'
import type { ChatMessage } from './store'

/** 生成唯一消息 ID。Generate unique message ID.
 *  @returns UUID 字符串，降级为时间戳+随机数。UUID string, fallback to timestamp+random. */
export function genId() {
  try { return crypto.randomUUID() } catch { return Date.now().toString(36) + Math.random().toString(36).slice(2, 8) }
}

/** 块列表 → 纯文本投影（text 字段的单一来源）：text/code 取正文、tool 行、
 *  question 加 ❓、answer/notice 原文；thinking/summary 不进投影。
 *  Blocks → plain-text projection (single source for the text field).
 *  text/code contribute their body; tool becomes a line; question gets ❓;
 *  answer/notice contribute verbatim; thinking/summary are excluded. */
export function textProjection(blocks: Block[]): string {
  const lines: string[] = []
  for (const b of blocks) {
    const p = b.payload || {}
    switch (b.type) {
      case 'text': if (p.md) lines.push(String(p.md)); break
      case 'code': if (p.code) lines.push(String(p.code)); break
      case 'tool': lines.push(`${p.name || ''}: ${String(p.output || '').slice(0, 200)}`); break
      case 'question': if (p.question) lines.push('❓ ' + p.question); break
      case 'answer': if (p.text) lines.push(String(p.text)); break
      case 'notice': if (p.text) lines.push(String(p.text)); break
    }
  }
  return lines.join('\n')
}

/** 添加消息到消息列表。Add message to message list.
 *  @param role - 消息角色。Message role.
 *  @param text - 消息文本（自动包装为 text 块）。Message text (wrapped into a text block). */
export function addMessage(role: ChatMessage['role'], text: string) {
  const blocks: Block[] = []
  if (text) blocks.push(makeBlock('text', { md: text, variant: 'bubble' }))
  messages.value.push({
    id: genId(),
    role,
    text: textProjection(blocks) || text,
    blocks,
    timestamp: Date.now(),
  })
  if (messages.value.length > MAX_MESSAGES) messages.value.shift()
}

/** 添加块消息（模块化入口：思考/工具/正文/提问/汇总等任意块序列）。
 *  Add a block message (modular entry: any block sequence).
 *  @param role - 消息角色。Message role.
 *  @param blocks - 块列表。Block list. */
export function addBlocks(role: ChatMessage['role'], blocks: Block[]) {
  messages.value.push({
    id: genId(),
    role,
    text: textProjection(blocks),
    blocks,
    timestamp: Date.now(),
  })
  if (messages.value.length > MAX_MESSAGES) messages.value.shift()
}

/** 清空所有消息和 token 使用量。Clear all messages and token usage. */
export function clearMessages() {
  messages.value = []
  tokenUsage.value = {}
}

/** 唤醒失败统一处理：错误状态 + 状态行 + 消息区醒目提示 + 自动展开面板。
 *  Unified wake failure handling: error state + status line + prominent message area hint + auto-expand panel.
 *  @param msg - 错误消息。Error message. */
export function failWake(msg: string) {
  state.value = 'error'
  statusLine.value = msg
  addMessage('system', '⚠️ ' + msg)
  expanded.value = true // 自动展开面板，确保用户看到错误信息。Auto-expand panel to ensure user sees error message.
}

/** 多轮历史构建（system 由后端各自注入；工具结果拼入 assistant content，供多轮引用）。
 *  块序列化：text 取 md、tool 取结果两行、question/answer 取问答两行；
 *  thinking/summary 不喂（防上下文膨胀）。
 *  Build multi-turn history (system injected by backend separately; tool results
 *  appended to assistant content for multi-turn reference). Block serialization:
 *  text takes md, tool its result lines, question/answer their pair; thinking and
 *  summary are not fed (keeps the context compact).
 *  @returns 包含最近 6 条消息的历史记录。History containing last 6 messages. */
export function buildHistory(): { role: string; content: string }[] {
  const history: { role: string; content: string }[] = []
  for (const m of messages.value.slice(-6)) {
    if (m.role === 'user') history.push({ role: 'user', content: m.text })
    else if (m.role === 'assistant') {
      // 有块序列化块（thinking/summary 跳过）；无块退化为 text 投影
      // Serialize blocks (thinking/summary skipped); fall back to the text projection.
      const parts: string[] = []
      for (const b of m.blocks || []) {
        const p = b.payload || {}
        if (b.type === 'text' && p.md) parts.push(String(p.md))
        else if (b.type === 'tool') parts.push(`[工具 ${p.name} 执行结果]\n${p.output || ''}`)
        else if (b.type === 'question') parts.push(`❓ ${p.question || ''}`)
        else if (b.type === 'answer') parts.push(String(p.text || ''))
        else if (b.type === 'code' && p.code) parts.push(String(p.code))
      }
      history.push({ role: 'assistant', content: parts.join('\n\n') || m.text })
    }
  }
  return history
}

/** 会话管理（控制台会话视图用）：新建 / 切换会话。
 *  Session management (for console session view): create / switch session.
 *  @param sessionId - 会话 ID，默认为空字符串。Session ID, defaults to empty string. */
export function createNewSession(sessionId = '') {
  messages.value = []
  tokenUsage.value = {}
  partialText.value = ''
  currentSessionId.value = sessionId
}

/** 切换到某会话：用其历史消息填充对话视图，设置当前会话 id。
 *  块结构随消息还原（blocks/turn_id/ts 透传；timestamp 取消息真实时间）。
 *  Switch to a session: populate conversation view with its history messages,
 *  set current session id. Block structure is restored (blocks/turn_id/ts pass
 *  through; timestamp uses the message's real time).
 *  @param sessionId - 目标会话 ID。Target session ID.
 *  @param msgs - 会话历史消息（含 blocks/ts）。Session history messages (with blocks/ts). */
export function switchSession(
  sessionId: string,
  msgs: { role: string; content: string; blocks?: Block[] | null; ts?: string | null }[],
) {
  messages.value = msgs
    .filter(m => m.role === 'user' || m.role === 'assistant')
    .map(m => {
      const blocks = m.blocks ?? (m.content ? [makeBlock('text', { md: m.content, variant: 'bubble' })] : [])
      const tsMs = m.ts ? Date.parse(m.ts) : NaN
      return {
        id: genId(),
        role: m.role as 'user' | 'assistant',
        text: m.content || textProjection(blocks),
        blocks,
        timestamp: isFinite(tsMs) ? tsMs : Date.now(),
      }
    })
  tokenUsage.value = {}
  pendingQuestion.value = null
  currentSessionId.value = sessionId
}
