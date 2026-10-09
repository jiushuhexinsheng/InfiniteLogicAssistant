import { state, statusLine, vadConfig, pendingQuestion, wakeKeywords, wakeMode, callActive, inOpenWindow, markTurnEnded } from '../store'
import { matchOption } from '../answerMatch'
import { detectWake, enterWakeCooldown, isWakeCooldown } from '../wakeMatch'
import { getChain, detectInChain } from './wakeChain'
import type { WakeProvider } from './types'
import {
  st, abandonPendingQuestion, beginTranscribe, endTranscribe, onUploadFailed,
  breakerAllows, playBeep, armCommandTimer, clearCommandTimer, armFollowupTimer,
  clearFollowupTimer, inEchoGuard,
} from './orchState'
// 拆分自 wakeOrchestrator.ts（重构：纯移动 + 状态收敛到 orchState.st，无行为变化）。
// Split from wakeOrchestrator.ts (pure move; mutable state consolidated into orchState.st).
// ── 云端转写 ──

async function transcribeSegment(blob: Blob): Promise<string> {
  const prev = beginTranscribe()
  try {
    const r = await st.deps!.api.transcribe(blob)
    return (r?.text || '').trim()
  } catch {
    onUploadFailed()
    return ''
  } finally {
    endTranscribe(prev)
  }
}

// ── 获取当前链（按模式） ──

function ensureChain(): WakeProvider[] {
  const mode = wakeMode.value
  if (mode !== st.lastMode) {
    st.currentChain = getChain(mode, st.deps!.api)
    st.lastMode = mode
  }
  return st.currentChain
}

// ── 处理一段音频（云端链路）──

/**
 * 处理一段音频：先看是不是在回答问题，否则做唤醒检测。
 *
 * Handle one audio segment: an answer first, wake detection otherwise.
 */
/** 段处理串行队列：VAD 可以背靠背出段，并发处理会交错穿过 await 空隙
 *  （两个段同时过「等指令中？」检查 → 双重触发/重复执行/重复录音）。
 *  公共入口 handleSegment 排队逐段执行，段与段不交叠。
 *  Serial segment queue: VAD can emit segments back-to-back; concurrent processing
 *  interleaves through the await gaps (two segments both pass the "awaiting command?"
 *  check → double fires / repeated execution / repeated prompts). The public
 *  handleSegment queues them so segments never interleave. */
let segmentChain: Promise<void> = Promise.resolve()

export function handleSegment(blob: Blob): Promise<void> {
  segmentChain = segmentChain
    .then(() => processSegment(blob))
    .catch((e) => console.warn('[wake] handleSegment error:', e))
  return segmentChain
}
// ── 通话漏斗 miss 的可见反馈（2026-10-07「我说话没有反应」根因修复）──
// 响应契约本就带 stage/reason（CallSegmentResponse 注释写明「供 audit 对照」），此前
// 前端刻意不读 → 漏斗 miss 全程静默，用户整场发言无任何反应。现在按 stage/reason
// 映射文案写入 statusLine（MiniPlayer 迷你条渲染）。
//
// Visible feedback for funnel misses (root-cause fix for 2026-10-07 "I speak and nothing
// happens"): the response contract already carries stage/reason, but the frontend
// deliberately ignored it — misses were fully silent. Map stage/reason to copy into
// statusLine (rendered by the MiniPlayer mini bar).
const MISS_STATUS: Record<string, string> = {
  'l0/no_session': '通话会话已过期，请重新双击进入',
  'l0/echo': '助手播报中，语音已忽略',
  'l0/too_short': '说话太短，未识别',
  'l0/low_rms': '声音太小，没听清',
  'l0/unfocused': '窗口未聚焦，语音未处理',
  'l1/empty': '没听清内容，请再说一次',
  'l1/too_short': '说话太短，未识别',
  'l1/filler': '只有语气词，未识别',
  'l1/incomplete': '似乎没说完，未识别',
  'l2/bystander': '未识别为指令（旁人/背景）',
  'l2/unsure': '没听懂这段话，请再说一次',
  error: '语音判定出错，请重试',
}

/** 按 stage/reason 得到 miss 文案；未知组合给中性兜底。Miss copy from stage/reason. */
function missStatusLine(stage?: string, reason?: string): string {
  if (!reason) return '未识别'
  const key = stage ? `${stage}/${reason}` : reason
  return MISS_STATUS[key] ?? MISS_STATUS[reason] ?? '未识别'
}

async function processSegment(blob: Blob) {
  if (!st.deps) return

  // TTS 回声窗口内的段整体丢弃：尾音/回声既不能唤醒，也不能被当作对提问的回答
  // （否则助手自己的声音会「替你回答」，问题一闪而过 —— 没法回答/极短）。
  // Drop segments inside the post-playback echo window outright: tail/echo audio must
  // neither wake the assistant nor answer a pending question (otherwise the assistant's
  // own voice answers for you and the question flashes by).
  if (inEchoGuard()) return

  // ⚠️ 熔断只作用于唤醒检测路径，不阻断答案/指令通道 ——
  // 答案和指令走的是 api.transcribe（不同端点），与唤醒检测的 api.wakeDetect 无关。
  // wakeDetect 挂了但 transcribe 正常时，语音作答仍应可用。
  //
  // The circuit breaker only guards the wake-detection path; answer and command channels
  // are NOT blocked — they use api.transcribe (a different endpoint) from api.wakeDetect.
  // Voice answering must stay available when wakeDetect is down but transcribe works.

  const pq = pendingQuestion.value
  if (pq) {
    st.turnToken++                 // 作废在飞的尾随提取：本段被消费为回答，任何迟到提取都不得再发
    const text = await transcribeSegment(blob)
    if (!text) return
    st.failures = 0
    // 待答先判唤醒词（纯本地拼音匹配，不打云端；转写复用不重复上传）：命中 → 弃题
    // 开新轮（顺带修掉「开口即被当答案」——半句话被当成本题回答投出去），未命中 →
    // 照旧走作答通道。裸命中 → 弃题后开指令窗（镜像 followup 分支语义）。
    // Wake check first while awaiting (purely local pinyin match, no cloud call; the
    // transcription is reused rather than re-uploaded): a hit abandons the question and
    // starts a fresh turn (also fixing "speaking up gets taken for the answer" — a
    // half-utterance delivered as this question's answer); a miss falls through to the
    // answering channel as before. A bare hit opens the command window after abandoning
    // (mirrors the followup branch's semantics).
    const wake = detectWake(text, wakeKeywords.value)
    if (wake.matched) {
      abandonPendingQuestion()
      if (wake.command) {
        st.turnToken++             // 认领发送权：作废在飞尾随提取。Claim sending rights.
        enterWakeCooldown()
        st.deps.sendText(wake.command)
      } else {
        st.awaitingCommand = true
        statusLine.value = '已唤醒，请说指令…'
        state.value = 'recording'
        armCommandTimer()
      }
      return
    }
    const hit = matchOption(text, pq.options)
    // 传段落捕获的问题快照：云端转写数秒内 pendingQuestion 可能被清（流错误竞态），
    // sendAnswer 内部不得重读 store（read-after-await 会让 qid 丢失 → 问答分开）。
    // Pass the question snapshot captured at segment start: during the multi-second
    // ASR await pendingQuestion may be cleared (stream-error race), and sendAnswer
    // must not re-read the store (that read-after-await loses the qid → Q/A split).
    await st.deps.sendAnswer(hit ? '' : text, hit?.value, 'voice', pq)
    return
  }

  // ── 通话模式（spec 2026-10-05）：作答分支之后优先于一切唤醒语义 ──
  // 段落直接进三级漏斗；命中才认领令牌送编排，未命中静默丢（audit 在后端）。
  // Call mode: after the answer branch, ahead of every wake semantic. The segment goes
  // straight into the funnel; only a hit claims the token and sends to the orchestrator,
  // misses are dropped silently (the backend audits).
  if (callActive.value) {
    // 终审 M1：通话态无论 callSegment 缺不缺成员都不落唤醒分支。生产里成员恒在 ——
    // 缺成员只可能来自测试假件，旧写法 `callActive && callSegment` 会把段落掩蔽进唤醒链
    // （假件掩蔽路由语义）。Final-review M1: inside a call never fall into the wake branch,
    // member or no member. The member is always present in production; absence is
    // test-double territory, and `callActive && callSegment` let a double route into wake.
    if (st.deps.api.callSegment) {
      const token = st.turnToken
      const r = await st.deps.api.callSegment(blob, {
        tabFocused: typeof document !== 'undefined' && document.hasFocus(),
        inOpenWindow: inOpenWindow(),
      }).catch((): { ok?: boolean; hit?: boolean; text?: string; stage?: string; reason?: string } => ({ ok: false }))
      if (token !== st.turnToken) return   // await 期间有更新交互认领 → 本段作废
      if (r?.ok && r.hit && r.text) {
        st.turnToken++
        markTurnEnded()
        if (state.value === 'recording') state.value = 'listening'
        statusLine.value = ''   // 清掉上一条 miss 提示，不残留
        st.deps.sendText(r.text)
      } else {
        // miss / 传输失败：给可见反馈（根因修复——此前静默丢弃，用户「说话没反应」）。
        // Feedback on miss/transport failure: silence was the root cause of "no reaction".
        statusLine.value = r?.ok
          ? missStatusLine(r.stage, r.reason)
          : '语音上传失败，请重试'
      }
    }
    return
  }

  if (st.awaitingCommand) {
    const token = st.turnToken     // 领取发送权令牌（在 await 之前捕获）
    const text = await transcribeSegment(blob)
    if (token !== st.turnToken) return   // 期间已有更新的交互认领 → 本段作废
    if (text) {
      st.awaitingCommand = false
      clearCommandTimer()
      statusLine.value = ''
      if (state.value === 'recording') state.value = 'listening'
      st.failures = 0
      st.turnToken++             // 认领：作废在飞的尾随提取（原子于发送）
      enterWakeCooldown()
      st.deps.sendText(text)
    } else {
      armCommandTimer()
    }
    return
  }

  // ── 续聊窗口（docs/designs/03-A）：窗口内的段免唤醒直接当新指令 ──
  // 位置在 pendingQuestion/st.awaitingCommand 之后（作答与指令窗优先）、熔断/节流之前
  // （与答案/指令同走 api.transcribe 通道，唤醒熔断不适用）。转写文本先过唤醒词判定：
  // 说中唤醒词照常进指令窗/直接执行（窗口与唤醒语义兼容），否则整句即指令。
  //
  // Follow-up window (docs/designs/03-A): segments inside the window become fresh
  // instructions without the wake word. Placed after pendingQuestion/st.awaitingCommand
  // (answering and the command window win) and before breaker/throttle (it rides the
  // api.transcribe channel like answers/commands, so the wake breaker does not apply).
  // The transcript is still wake-word checked: a wake word opens the command window /
  // runs its command as usual (the window stays compatible with wake semantics);
  // otherwise the whole sentence is the instruction.
  if (state.value === 'followup') {
    const token = st.turnToken
    const text = await transcribeSegment(blob)
    if (token !== st.turnToken) return
    if (!text) { armFollowupTimer(); return }   // 空转写：窗口续期。Empty transcript: keep the window.
    st.failures = 0
    const r = detectWake(text, wakeKeywords.value)
    if (r.matched) {
      if (r.command) {
        st.turnToken++
        enterWakeCooldown()
        clearFollowupTimer()
        st.deps.sendText(r.command)
      } else {
        st.awaitingCommand = true
        statusLine.value = '已唤醒，请说指令…'
        state.value = 'recording'
        armCommandTimer()
      }
      return
    }
    st.turnToken++              // 认领：作废在飞的尾随提取。Claim: void in-flight extraction.
    clearFollowupTimer()     // 状态随 sendText → runTurn 走 thinking，计时器一并收（双保险）。
    st.deps.sendText(text)
    return
  }

  // 熔断：只阻断唤醒检测上传（答案/指令通道不受影响，见上方说明）；
  // 冷静期（60s）过后自动放行试探，不再永久静默。
  // Circuit break: only blocks wake-detection uploads (answer/command channels
  // unaffected); after the cooldown (60s) a probe is allowed — no permanent silence.
  if (!breakerAllows()) return

  const now = Date.now()
  if (now - st.lastUploadAt < vadConfig.upload_throttle_ms) return
  st.lastUploadAt = now

  const mode = wakeMode.value
  if (mode === 'webspeech') return

  // 唤醒冷却：刚发过指令/作答后的短窗口内不再判定唤醒词（防指令回声被当成新唤醒）。
  // 冷却此前只在 Web Speech 路径检查，云端/KWS 路径漏检 —— 武装了却从不生效。
  // Wake cooldown: no wake judging shortly after a command/answer was sent (a command's
  // own echo must not fire a fresh wake). The cooldown used to be checked only on the
  // Web Speech path — armed on all paths, enforced on one.
  if (isWakeCooldown()) return

  // ── 判定与提取分离（本地/auto）：KWS 快检先动作，指令提取后台跑 ──
  // 本地 KWS 毫秒级确认唤醒词 → 立即提示音 + 进入等指令窗口（动作先行，不等任何
  // 「二次确认」）；同一段里可能带的指令（「衍衡，查天气」）由后台 /voice/wake
  // 转写提取，提到就直接执行、提不到就保持窗口等你说。
  // cloud 模式跳过快检：上传 → ASR 文本判定 → 动作（云端说了算，慢是本性）。
  //
  // Verdict first, extraction later (local/auto): local KWS confirms the wake word
  // in milliseconds → immediate chime + command window (act now, no re-confirmation);
  // any command carried in the same clip is extracted in the background via
  // /voice/wake — if found it executes at once, otherwise the window stays open.
  // cloud mode skips the check: upload → ASR text verdict → act (the cloud decides,
  // and that is inherently slow).
  if (mode !== 'cloud') {
    let check: { ok?: boolean; hit?: boolean; bypass?: boolean }
    try {
      check = await st.deps.api.wakeCheck(blob)
    } catch {
      onUploadFailed()
      return
    }
    if (!check?.ok) {
      onUploadFailed()
      return
    }
    if (check.bypass) {
      // KWS 闸门不可用 → 回退完整路径（云端判定），不丢唤醒。
      // Gate unavailable → fall back to the full path (cloud judging); never lose the wake.
      await fullDetect(ensureChain(), blob)
      return
    }
    if (!check.hit) return   // 未命中：丢弃，不出本机、零成本
    st.failures = 0

    // ── 命中：立即动作 ──
    st.awaitingCommand = true
    statusLine.value = '已唤醒，请说指令…'
    if (state.value === 'listening') state.value = 'recording'
    playBeep()
    armCommandTimer()
    void extractTrailingCommand(blob, mode)   // 不 await：后台提取尾随指令
    return
  }

  await fullDetect(ensureChain(), blob)
}
/**
 * 后台提取同一段音频里尾随唤醒词的指令（一句话场景「衍衡，查天气」）。
 * 提到 → 直接执行并收回指令窗口；提不到 → 窗口保持，等操作者说指令。
 * 失败不打断已开的窗口（两步式照常可用）。
 *
 * Background-extract the command trailing the wake word in the same clip (the
 * one-sentence case "衍衡，查天气"). Found → execute at once and retract the
 * window; not found → keep the window open. Failures never disturb the open
 * window (the two-step flow keeps working).
 */
async function extractTrailingCommand(blob: Blob, mode: string) {
  if (!st.deps) return
  const token = st.turnToken          // await 之前捕获令牌
  try {
    const r = await st.deps.api.wakeDetect(blob, { mode })
    if (token !== st.turnToken) return     // 已被更新的交互认领 → 丢弃（防双重执行）
    if (r?.ok && r.command) {
      st.turnToken++                     // 认领发送权（原子于下面的 sendText）
      st.awaitingCommand = false
      clearCommandTimer()
      statusLine.value = ''
      if (state.value === 'recording') state.value = 'listening'
      enterWakeCooldown()
      st.deps.sendText(r.command)
    }
  } catch {
    /* 提取失败不影响已开的指令窗口 */
  }
}

/** 完整判定路径（cloud 模式 / KWS 旁路回退）：上传 → ASR 文本判定 → 动作。
 *  Full judging path (cloud mode / KWS-bypass fallback): upload → ASR text verdict → act. */
async function fullDetect(chain: ReturnType<typeof ensureChain>, blob: Blob) {
  if (!st.deps) return
  if (chain.length === 0) return
  const prev = beginTranscribe()
  let result: { matched: boolean; command: string }
  try {
    result = await detectInChain(chain, blob, wakeKeywords.value)
  } catch {
    onUploadFailed()
    return
  } finally {
    endTranscribe(prev)
  }

  if (!result.matched) return
  st.failures = 0
  statusLine.value = ''

  if (result.command) {
    st.turnToken++                 // 认领发送权
    enterWakeCooldown()
    st.deps.sendText(result.command)
    return
  }

  st.awaitingCommand = true
  statusLine.value = '已唤醒，请说指令…'
  if (state.value === 'listening') state.value = 'recording'
  playBeep()
  armCommandTimer()
}
