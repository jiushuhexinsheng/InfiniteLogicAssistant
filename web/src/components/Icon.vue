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
  Settings, Volume2,
} from 'lucide-vue-next'

// name → lucide 图标映射（保持既有用法透明，并可随时补充新图标）
const ICONS: Record<string, Component> = {
  // 状态
  wave: AudioWaveform,
  ear: Ear,
  mic: Mic,
  sparkles: Sparkles,
  brain: Brain,
  wrench: Wrench,
  chat: MessageSquare,
  check: Check,
  alert: CircleAlert,
  // 工具 / 操作
  search: Search,
  send: Send,
  trash: Trash2,
  'chevron-down': ChevronDown,
  close: X,
  play: Play,
  stop: Square,
  dots: Ellipsis,
  user: User,
  // 补充（开始页特性卡等）
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
}

const props = withDefaults(defineProps<{ name: string; size?: number }>(), { size: 18 })

const strokeWidth = 1.8
const icon = computed(() => ICONS[props.name] || CircleAlert)
</script>
