import { ref } from 'vue'

/** 控制台标签页键类型。Console tab key type. */
export type ConsoleTabKey = 'conv' | 'task' | 'status' | 'tools' | 'stats' | 'env' | 'memory' | 'settings' | 'history' | 'schedule'

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
  { key: 'schedule', label: '定时', icon: 'calendar-clock' },
]

/** 模块级单例：ConsolePage 与其懒加载子视图（如 ConsoleHistory）必须共享同一 activeTab，
 *  否则子视图里 `activeTab.value = 'conv'` 只改到自己的本地 ref，无法真正切换控制台视图。
 *  Module-level singleton: ConsolePage and its lazy-loaded subviews (e.g., ConsoleHistory) must share the same activeTab,
 *  otherwise `activeTab.value = 'conv'` in subviews only changes their local ref, unable to actually switch console views. */
const activeTab = ref<ConsoleTabKey>('conv')

/** 控制台状态管理 composable。Console state management composable.
 *  @returns 包含活动标签页的响应式引用。Contains reactive reference of active tab. */
export function useConsole() {
  return { activeTab }
}
