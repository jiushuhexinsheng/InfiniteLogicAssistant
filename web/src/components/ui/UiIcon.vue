<template>
  <component :is="icon" :size="size" :stroke-width="strokeWidth" aria-hidden="true" />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Component } from 'vue'
import {
  AudioWaveform, Ear, Mic, Sparkles, Brain, Wrench, MessageSquare, MessagesSquare, Check, CircleAlert,
  Search, Send, Trash2, ChevronDown, ChevronRight, ArrowDown, X, Play, Square, Ellipsis, User,
  Globe, CalendarClock, Database, Bot, Zap, Clock, Infinity as InfinityIcon,
  Settings, Volume2, Plus, CirclePlus, Activity, BarChart3, History, List, Sun, Moon, Loader2,
  Copy, FileText, Image as ImageIcon, Shield, Library,
} from 'lucide-vue-next'

/**
 * name → lucide 图标映射（统一入口，可随时补充新图标）。
 * Name-to-Lucide icon mapping; centralized entry point, easily extendable.
 */
const ICONS: Record<string, Component> = {
  wave: AudioWaveform,
  ear: Ear,
  mic: Mic,
  sparkles: Sparkles,
  brain: Brain,
  wrench: Wrench,
  chat: MessageSquare,
  check: Check,
  alert: CircleAlert,
  search: Search,
  send: Send,
  trash: Trash2,
  'chevron-down': ChevronDown,
  'chevron-right': ChevronRight,
  'arrow-down': ArrowDown,
  close: X,
  play: Play,
  stop: Square,
  dots: Ellipsis,
  user: User,
  globe: Globe,
  'calendar-clock': CalendarClock,
  database: Database,
  bot: Bot,
  zap: Zap,
  clock: Clock,
  infinity: InfinityIcon,
  'messages-square': MessagesSquare,
  settings: Settings,
  volume: Volume2,
  plus: Plus,
  'circle-plus': CirclePlus,
  // 控制台侧边栏 Console sidebar
  activity: Activity,
  'bar-chart': BarChart3,
  history: History,
  list: List,
  sun: Sun,
  moon: Moon,
  'loader-2': Loader2,
  // 消息块 Message blocks
  copy: Copy,
  'file-text': FileText,
  image: ImageIcon,
  // 设置页菜单 / 控制台侧栏 Settings menu / console sidebar
  shield: Shield,
  library: Library,
}

/** 图标组件 Props：图标名称(对应 ICONS 映射表键)/图标尺寸(像素)。Icon props: icon name (key in ICONS map), size in pixels. */
const props = withDefaults(defineProps<{ name: string; size?: number }>(), { size: 18 })
const strokeWidth = 1.8
/**
 * 取图标组件；未注册的名字回退成 CircleAlert。
 *
 * ⚠️ 回退是**静默**的 —— `configDefs.ts` 的 `icon:'shield'` 与 `useConsole.ts` 的
 * `icon:'library'` 都因此长期显示成圆圈感叹号，而 `MenuDef.icon` 只是 `string`、没有任何类型
 * 约束能拦住它。dev 期补一条告警，别再让下一个未注册名悄悄上线。
 *
 * Icon component lookup with a CircleAlert fallback.
 *
 * ⚠️ The fallback is **silent** — `configDefs.ts`'s `icon:'shield'` and `useConsole.ts`'s
 * `icon:'library'` both rendered as an alert circle for a long time, and `MenuDef.icon` is just
 * `string`, so nothing in the type system caught it. A dev-only warning stops the next
 * unregistered name from shipping quietly.
 */
const icon = computed(() => {
  const found = ICONS[props.name]
  if (!found && import.meta.env.DEV) {
    console.warn(`[UiIcon] 未注册的图标名「${props.name}」—— 已回退成 CircleAlert，请在 ICONS 表补上。`)
  }
  return found || CircleAlert
})
</script>
