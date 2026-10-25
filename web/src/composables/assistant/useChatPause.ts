import { computed, ref } from 'vue'
import { api } from '../../api'
import { currentSessionId, state } from './store'

/** 暂停档位（与后端 PauseMode 对齐）：wait = 到步骤边界停；stop = 立即中断 LLM；
 *  force = LLM 与在途工具都中断。前端默认 stop —— 用户要的是「LLM 也暂停」。
 *  Pause modes (mirroring the backend PauseMode): wait = stop at the step boundary;
 *  stop = abort the LLM now; force = abort both the LLM and in-flight tools. The
 *  frontend defaults to stop — the user asked for "pause the LLM too". */
export type PauseMode = 'wait' | 'stop' | 'force'

/** 回合进行中的状态集合（与 useChat 的排队判定一致）。
 *  States in which a turn is genuinely running (same set useChat queues on). */
const RUNNING_STATES = ['thinking', 'tool_calling', 'responding']

/** 是否处于暂停（本地镜像；后端是权威）。Local mirror of the paused flag (the backend is authoritative). */
export const paused = ref(false)

/** 回合是否在跑（决定暂停/停止按钮的显隐）。暂停时即使状态已回基线也算在跑 ——
 *  服务端执行循环仍挂起在闸门上，等恢复。
 *  Whether a turn is live (drives the pause/stop buttons). A paused turn still counts
 *  as live even if the state fell back to baseline — the server loop is parked at the
 *  gate waiting for resume. */
export const turnActive = computed(() => paused.value || RUNNING_STATES.includes(state.value))

/**
 * 暂停当前回合（默认 safe stop：中断 LLM 生成，保留已生成部分）。
 * Pause the current turn (safe stop by default: abort generation, keep what was produced).
 *
 * @param mode 暂停档位。Pause mode.
 * @returns 是否成功进入暂停。Whether the pause was accepted.
 */
export async function pauseTurn(mode: PauseMode = 'stop'): Promise<boolean> {
  const sid = currentSessionId.value
  if (!sid) return false
  try {
    await api.pauseTask(sid, mode)
    paused.value = true
    return true
  } catch {
    // 会话可能刚好收尾（404）：不要把 UI 留在假的「已暂停」。
    // The run may have just finished (404): never leave the UI falsely "paused".
    paused.value = false
    return false
  }
}

/**
 * 恢复被暂停的回合。Resume a paused turn.
 *
 * @returns 是否成功恢复。Whether the resume was accepted.
 */
export async function resumeTurn(): Promise<boolean> {
  const sid = currentSessionId.value
  paused.value = false
  if (!sid) return false
  try {
    await api.resumeTask(sid)
    return true
  } catch {
    return false
  }
}

/** 在暂停与继续之间切换（按钮的唯一入口）。Toggle pause/resume (the button's single entry). */
export async function togglePause(): Promise<void> {
  if (paused.value) await resumeTurn()
  else await pauseTurn()
}

/** 回合收尾（done / abort / error）时清掉本地暂停标志；后端已自然结束，无需恢复请求。
 *  Clear the local paused flag when a turn wraps up (done / abort / error); the
 *  backend already finished, so no resume request is needed. */
export function resetPause(): void {
  paused.value = false
}
