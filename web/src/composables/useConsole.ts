import { ref } from 'vue'
import { api } from '../api'
import { createNewSession } from './assistant/store'
import { notify } from './useToast'
import { formatError } from '../errors'

/** 控制台标签页键类型。Console tab key type. */
export type ConsoleTabKey = 'conv' | 'task' | 'status' | 'tools' | 'stats' | 'env' | 'memory' | 'settings' | 'history' | 'library' | 'schedule'

/** 控制台标签页接口。Console tab interface. */
export interface ConsoleTab {
  /** 标签页键。Tab key. */
  key: ConsoleTabKey
  /** 标签页显示文本。Tab display label. */
  label: string
  /** 标签页图标名称。Tab icon name. */
  icon: string
}

/** 控制台导航定义（单一来源，侧边栏 / 视图切换共用）。
 *  Console navigation definitions (single source of truth, shared between sidebar and view switching). */
export const CONSOLE_TABS: ConsoleTab[] = [
  { key: 'conv', label: '对话', icon: 'messages-square' },
  { key: 'task', label: '任务', icon: 'zap' },
  { key: 'status', label: '状态', icon: 'activity' },
  { key: 'tools', label: '工具', icon: 'wrench' },
  { key: 'stats', label: '统计', icon: 'bar-chart' },
  { key: 'env', label: '环境', icon: 'globe' },
  { key: 'memory', label: '记忆', icon: 'database' },
  { key: 'settings', label: '设置', icon: 'settings' },
  { key: 'history', label: '历史', icon: 'history' },
  { key: 'library', label: '任务库', icon: 'library' },
  { key: 'schedule', label: '定时', icon: 'calendar-clock' },
]

/** 模块级单例：ConsolePage 与其懒加载子视图（如 ConsoleHistory）必须共享同一 activeTab，
 *  否则子视图里 `activeTab.value = 'conv'` 只改到自己的本地 ref，无法真正切换控制台视图。
 *  Module-level singleton: ConsolePage and its lazy-loaded subviews (e.g., ConsoleHistory) must share the same activeTab,
 *  otherwise `activeTab.value = 'conv'` in subviews only changes their local ref, unable to actually switch console views. */
const activeTab = ref<ConsoleTabKey>('conv')

/** 侧栏折叠态持久化键（localStorage）。Sidebar collapse persistence key. */
const SIDEBAR_KEY = 'xluo.consoleSidebarCollapsed'
/** 侧栏是否折叠（模块单例，跨挂载存活；持久化到 localStorage）。
 *  Whether the sidebar is collapsed (module singleton surviving mount/unmount;
 *  persisted to localStorage). */
const sidebarCollapsed = ref(tryGet())

function tryGet(): boolean {
  try { return localStorage.getItem(SIDEBAR_KEY) === '1' } catch { return false }
}

/** 切换侧栏折叠并持久化。Toggle the sidebar collapse and persist. */
function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
  try { localStorage.setItem(SIDEBAR_KEY, sidebarCollapsed.value ? '1' : '0') } catch { /* 隐私模式忽略 */ }
}

/** 新建会话：清空当前对话，开启新的独立对话线（侧栏「新建」触发；原先内联在
 *  ConsoleConversation，随按钮移到左侧栏一并迁来）。
 *  Create a new session: clear the current conversation and start a fresh thread (fired
 *  by the sidebar's New button; moved here from ConsoleConversation along with the button). */
export async function newSession(): Promise<void> {
  try {
    const r = await api.createSession()
    createNewSession(r.session.id)
    activeTab.value = 'conv'   // 新建后回到对话页。Return to the conversation tab.
    notify.ok('已新建会话')
  } catch (e) {
    notify.err('新建会话失败：' + formatError(e))
  }
}

/** 控制台状态管理 composable。Console state management composable.
 *  @returns 活动标签页、侧栏折叠态与会话操作。Active tab, sidebar collapse state and session actions. */
export function useConsole() {
  return { activeTab, sidebarCollapsed, toggleSidebar, newSession }
}
