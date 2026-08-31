import { ref } from 'vue'

export type ConsoleTabKey = 'conv' | 'task' | 'status' | 'tools' | 'stats' | 'env' | 'memory' | 'settings' | 'history' | 'schedule'

export interface ConsoleTab {
  key: ConsoleTabKey
  label: string
  icon: string
}

// 控制台导航定义（单一来源，侧边栏 / 视图切换共用）
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

// 模块级单例：ConsolePage 与其懒加载子视图（如 ConsoleHistory）必须共享同一 activeTab，
// 否则子视图里 `activeTab.value = 'conv'` 只改到自己的本地 ref，无法真正切换控制台视图。
const activeTab = ref<ConsoleTabKey>('conv')

export function useConsole() {
  return { activeTab }
}
