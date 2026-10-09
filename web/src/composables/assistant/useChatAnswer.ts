import { api } from '../../api'
import { formatError } from '../../errors'
import { messages, pendingQuestion, currentSessionId, addBlocks, addMessage } from './store'
import type { PendingQuestion } from './store'
import { stopSpeak } from './useTts'
import { attachAnswer, makeBlock } from '../../blocks/normalize'

/** 回答澄清/确认问题（解除后端 ask() 阻塞）。
 *  Answer clarification/confirmation question (unblock backend ask() call).
 *  @param text - 用户回答文本（选择类提问为空）。User answer text (empty for choice questions).
 *  @param choice - 结构化选择的取值（由选项按钮回传）。The structured selection returned by the option buttons.
 *  @param source - 作答通道（typed/voice/button），语音作答可审计。Answer channel (voice answers auditable).
 *  @param question - 作答对象快照（语音段落在转写前捕获）；缺省取 store 现值。
 *    云端转写要等数秒，期间 pendingQuestion 可能被清（流错误/中止竞态）—— 传快照
 *    让 qid 与贴块绑定「段落当时在回答的那个问题」，不因 store 已空而走独立气泡兜底
 *    （那正是「回答和问题分开」）。The question snapshot the answer binds to (voice
 *    segments capture it before ASR); defaults to the current store value. Cloud ASR
 *    takes seconds and pendingQuestion may be cleared meanwhile (stream error/abort
 *    race) — the snapshot keeps the qid and attach target bound to the question the
 *    segment was answering, instead of falling to the standalone-bubble fallback when
 *    the store is empty (which is exactly "answer and question split apart"). */
export async function sendAnswer(
  text: string,
  choice?: string,
  source: string = 'typed',
  question?: PendingQuestion | null,
) {
  const t = text.trim()
  // 结构化选择可以不带文本；两者皆空则不投递（避免空回答解除后端阻塞）。
  // A structured choice may carry no text; when both are empty, don't deliver
  // (avoiding an empty answer that would unblock the backend).
  if (!t && !choice) return
  if (!currentSessionId.value) return
  // 作答对象：调用方快照优先（语音路径），否则 store 现值（按钮/输入框同步路径）。
  // Answer target: the caller's snapshot first (voice path), else the current store
  // value (button/input paths, synchronous — no await gap).
  const target = question ?? pendingQuestion.value
  // 记录用文本：选择类取被选选项的 label（人类可读），文本类取输入文本。
  // Record text: a choice takes the selected option's label (human-readable), a text answer its own text.
  const qid = target?.qid
  const label = choice
    ? (target?.options.find((o) => o.value === choice)?.label || choice)
    : t
  try {
    await api.answer(currentSessionId.value, t, choice, { qid, source })
    // 仅在投递成功后写记录，避免记录与后端状态不一致。
    // Record only after a successful delivery, so the record cannot disagree with the backend.
    // 配对问题在某条消息里 → 答案贴进该卡片（问题块紧后，修「问题和回答分离」）；
    // 找不到（无 qid / 流已死）才落独立用户气泡兜底。
    // Paired question lives in a message → attach the answer into that card right
    // after the question block (fixes Q/A split apart); fall back to a standalone
    // user bubble only when no holder exists (no qid / dead stream).
    const holder = qid
      ? messages.value.find(m => m.blocks?.some(b => b.type === 'question' && b.payload.qid === qid))
      : undefined
    if (qid && holder?.blocks) {
      attachAnswer(holder.blocks, { qid, text: label, choice: choice ?? null, source })
    } else {
      addBlocks('user', [makeBlock('answer', { qid, text: label, choice: choice ?? null, source })])
    }
    // 只清「本次作答的那个问题」：快照路径下 store 可能已是另一个新问题，不得误清。
    // Clear only the question this answer belongs to: on the snapshot path the store
    // may already hold a different, newer question — it must not be wiped.
    if (!pendingQuestion.value || pendingQuestion.value.qid === qid) pendingQuestion.value = null
    // 已作答：问题还在被朗读的话就停掉（用户已经用行动回答了，不必念完）。
    // Answered: stop the question reading if it is still going (the user already
    // answered by action; it need not finish reading).
    stopSpeak('new_turn')
    // 诊断观测点：投递后记录 qid/配对结果，问答若再「分开」可据此定位（兜底 or 贴块）。
    // Diagnostic probe: log qid/attach outcome after delivery so a future Q/A split can
    // be attributed (fallback vs attach) from the console.
    console.debug('[Asst] answer delivered', { qid, paired: !!holder, source })
  } catch (e) {
    addMessage('system', '回答投递失败：' + formatError(e))
  }
}
