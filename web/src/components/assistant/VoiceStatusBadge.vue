<template>
  <!-- 语音状态徽章：每种状态独立颜色与动效（聆听呼吸环 / 通话双环 / 思考三点…）。
       Voice status badge: each state gets its own colour and effect. -->
  <span class="vsb" :class="`k-${kind}`">
    <span class="vsb-mark" aria-hidden="true">
      <span v-if="kind === 'ready'" class="vsb-check">✓</span>
      <span v-else-if="kind === 'error'" class="vsb-alert">!</span>
      <span v-else-if="kind === 'recognizing'" class="vsb-spin"></span>
      <span v-else-if="kind === 'thinking'" class="vsb-dots"><i></i><i></i><i></i></span>
      <span v-else-if="kind === 'responding'" class="vsb-eq"><i></i><i></i><i></i></span>
      <span v-else class="vsb-dot"></span>
      <span v-if="ring" class="vsb-ring"></span>
    </span>
    <span class="vsb-label">{{ label }}</span>
  </span>
</template>

<script setup lang="ts">
/** 语音状态徽章（纯展示）。Voice status badge (presentational). */
import { computed } from 'vue'

export type VoiceStatusKind =
  | 'idle' | 'listening' | 'call' | 'command' | 'recognizing' | 'ready'
  | 'ghost' | 'thinking' | 'tool' | 'responding' | 'awaiting' | 'standby' | 'error'

const props = withDefaults(defineProps<{
  kind: VoiceStatusKind
  /** 唤醒词（静待时用于提示怎么说）。Wake word shown in standby. */
  wakeWord?: string
}>(), { wakeWord: '' })

/** 状态文案。State labels. */
const LABELS: Record<VoiceStatusKind, string> = {
  idle: '双击开启语音',
  listening: '聆听',
  call: '通话中',
  command: '请说',
  recognizing: '识别',
  ready: '就绪',
  ghost: '旁白',
  thinking: '思考',
  tool: '工具',
  responding: '回复',
  awaiting: '待答',
  standby: '静待',
  error: '错误',
}

/** 实际文案：静待时提示用唤醒词唤醒。Display label (standby prompts the wake word). */
const label = computed(() =>
  props.kind === 'standby' && props.wakeWord
    ? `说「${props.wakeWord}」唤醒`
    : LABELS[props.kind])

/** 需要呼吸环的状态。States with the breathing ring. */
const ring = computed(() =>
  ['listening', 'call', 'command', 'awaiting', 'recognizing'].includes(props.kind))
</script>

<style scoped>
.vsb {
  --c: #94a3b8;
  display: inline-flex; align-items: center; gap: 5px;
  height: 24px; padding: 0 9px; border-radius: 999px;
  border: 1px solid color-mix(in srgb, var(--c) 45%, transparent);
  background: color-mix(in srgb, var(--c) 10%, transparent);
  color: var(--c); font-size: 11px; line-height: 1; white-space: nowrap;
  transition: color var(--dur-base), border-color var(--dur-base), background var(--dur-base);
}
.vsb-mark { position: relative; width: 11px; height: 11px; display: grid; place-items: center; flex: none; }
.vsb-label { color: inherit; opacity: .95; }

/* 圆点与呼吸环。Dot and breathing ring. */
.vsb-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--c); box-shadow: 0 0 6px color-mix(in srgb, var(--c) 75%, transparent); }
.vsb-ring {
  position: absolute; inset: -1px; border-radius: 50%;
  border: 1px solid color-mix(in srgb, var(--c) 55%, transparent);
  animation: vsb-ring 1.7s ease-out infinite;
}
@keyframes vsb-ring { 0% { transform: scale(.6); opacity: .9; } 100% { transform: scale(2); opacity: 0; } }

/* 识别：转圈。Recognizing: spinner. */
.vsb-spin {
  width: 10px; height: 10px; border-radius: 50%;
  border: 2px solid color-mix(in srgb, var(--c) 25%, transparent);
  border-top-color: var(--c); animation: vsb-spin .8s linear infinite;
}
@keyframes vsb-spin { to { transform: rotate(360deg); } }

/* 思考：三点跳动。Thinking: bouncing dots. */
.vsb-dots { display: flex; align-items: center; gap: 2px; }
.vsb-dots i { width: 3px; height: 3px; border-radius: 50%; background: var(--c); animation: vsb-bounce 1.1s ease-in-out infinite; }
.vsb-dots i:nth-child(2) { animation-delay: .15s; }
.vsb-dots i:nth-child(3) { animation-delay: .3s; }
@keyframes vsb-bounce { 0%, 60%, 100% { transform: translateY(0); opacity: .55; } 30% { transform: translateY(-3px); opacity: 1; } }

/* 回复：小均衡条。Responding: mini equalizer. */
.vsb-eq { display: flex; align-items: flex-end; gap: 1.5px; height: 9px; }
.vsb-eq i { width: 2px; border-radius: 1px; background: var(--c); animation: vsb-eq .9s ease-in-out infinite; }
.vsb-eq i:nth-child(1) { height: 4px; }
.vsb-eq i:nth-child(2) { height: 8px; animation-delay: .15s; }
.vsb-eq i:nth-child(3) { height: 5px; animation-delay: .3s; }
@keyframes vsb-eq { 50% { transform: scaleY(.45); } }

/* 就绪/错误。Ready / error. */
.vsb-check { font-size: 11px; font-weight: 700; }
.vsb-alert { font-size: 11px; font-weight: 700; }

/* 各状态颜色。Per-state colours. */
.k-idle { --c: #94a3b8; }
.k-listening { --c: #22d3ee; }
.k-call { --c: #34d399; background: color-mix(in srgb, var(--c) 14%, transparent); box-shadow: 0 0 12px color-mix(in srgb, var(--c) 22%, transparent); }
.k-call .vsb-ring { animation-duration: 1.3s; }
.k-command { --c: #38bdf8; }
.k-recognizing { --c: #60a5fa; }
.k-ready { --c: #34d399; background: color-mix(in srgb, var(--c) 16%, transparent); box-shadow: 0 0 14px color-mix(in srgb, var(--c) 25%, transparent); animation: vsb-flash .6s ease-out 1; }
@keyframes vsb-flash { 0% { box-shadow: 0 0 0 color-mix(in srgb, var(--c) 0%, transparent); } 40% { box-shadow: 0 0 18px color-mix(in srgb, var(--c) 45%, transparent); } 100% { box-shadow: 0 0 14px color-mix(in srgb, var(--c) 25%, transparent); } }
.k-ghost { --c: #94a3b8; border-style: dashed; background: transparent; }
.k-thinking { --c: #a78bfa; }
.k-tool { --c: #fbbf24; }
.k-responding { --c: #2dd4bf; }
.k-awaiting { --c: #fbbf24; }
.k-standby { --c: #64748b; }
.k-error { --c: #f87171; background: color-mix(in srgb, var(--c) 14%, transparent); animation: vsb-shake .5s ease-in-out 2; }
@keyframes vsb-shake { 25% { transform: translateX(-1.5px); } 75% { transform: translateX(1.5px); } }

@media (prefers-reduced-motion: reduce) {
  .vsb-ring, .vsb-spin, .vsb-dots i, .vsb-eq i, .k-ready, .k-error { animation: none; }
}
</style>
