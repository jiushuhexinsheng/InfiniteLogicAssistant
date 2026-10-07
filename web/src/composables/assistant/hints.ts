/**
 * 入口提示文案 —— 单一事实源，随唤醒开关走（2026-10-07 遗留审计）。
 *
 * 唤醒未开启时，StartPage 副标题、面板空态、控制台横幅仍叫用户「说唤醒词」——
 * 提示与行为不一致（说了也没有监听方）。三处句子结构不同但分支逻辑相同，
 * 收口到纯函数：一处测试覆盖全部分支，组件只做插值。
 *
 * Entry-prompt copy — single source of truth, driven by the wake switch
 * (2026-10-07 leftover audit). With wake disabled, the StartPage subtitle, panel empty
 * state and console banner still told the user to say the wake word — copy contradicting
 * behavior (nobody was listening). The three sentences differ in structure but share one
 * branch, so they live in pure functions: one test file covers every branch and the
 * components only interpolate.
 */

/**
 * StartPage 副标题：唤醒开时保留唤醒提示并补上双击通话入口；唤醒关时不再喊唤醒词。
 * StartPage subtitle: wake on keeps the wake hint and adds the double-click call entry;
 * wake off never tells the user to shout a wake word.
 */
export function startSubtitle(wakeOn: boolean, hint: string): string {
  return wakeOn
    ? `说${hint}唤醒 · 双击悬浮球开通话 · 或直接输入文字开聊`
    : `双击悬浮球开通话 · 或直接输入文字开聊`
}

/**
 * 面板空态提示：唤醒开保持原句；唤醒关给出文字/双击通话两条出路。
 * Panel empty-state hint: wake on keeps the original sentence; wake off offers text and
 * double-click call as the two ways in.
 */
export function emptyHint(wakeOn: boolean, hint: string): string {
  return wakeOn ? `输入文字，或说${hint}唤醒` : `输入文字，或双击悬浮球开通话`
}

/**
 * 控制台欢迎横幅状态段：唤醒开保持原句；唤醒关明示已关闭。
 * Console welcome-banner status segment: wake on keeps the original; wake off says so.
 */
export function consoleBanner(wakeOn: boolean, hint: string): string {
  return wakeOn ? `在线 · 说${hint}唤醒` : '在线 · 语音唤醒已关'
}
