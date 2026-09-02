<template>
  <component :is="icon" :size="size" :stroke-width="strokeWidth" aria-hidden="true" />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Component } from 'vue'
import {
  AudioWaveform, Ear, Mic, Sparkles, Brain, Wrench, MessageSquare, MessagesSquare, Check, CircleAlert,
  Search, Send, Trash2, ChevronDown, X, Play, Square, Ellipsis, User,
  Globe, CalendarClock, Database, Bot, Zap, Clock, Infinity as InfinityIcon,
  Settings, Volume2, Plus, CirclePlus, Activity, BarChart3, History, List, Sun, Moon, Loader2,
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
}

/** 图标组件 Props：图标名称(对应 ICONS 映射表键)/图标尺寸(像素)。Icon props: icon name (key in ICONS map), size in pixels. */
const props = withDefaults(defineProps<{ name: string; size?: number }>(), { size: 18 })
const strokeWidth = 1.8
const icon = computed(() => ICONS[props.name] || CircleAlert)
</script>
