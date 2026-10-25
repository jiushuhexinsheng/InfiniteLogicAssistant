<template>
  <!-- 语音条：原小胶囊 + 有识别文本时向右伸出的文本段。
       Voice bar: the original small pill, extending right into a text segment when there
       is recognition text. -->
  <button
    type="button"
    class="voice-hud"
    :class="[`side-${side}`, { ready: accepted, ghost, hidden: !visible }]"
    :style="hudStyle"
    :aria-label="ariaLabel"
    @click="$emit('open')"
  >
    <!-- 文本段（仅识别阶段出现）。Text segment, shown only while there is transcript text. -->
    <span v-if="showBox" class="vh-box">
      <span class="vh-body">
        <span class="vh-role">衍衡</span>
        <span class="vh-text">{{ transcriptText }}<span v-if="recognizing" class="vh-caret" aria-hidden="true"></span></span>
      </span>
      <span class="vh-end">
        <span v-if="indicator === 'spinner'" class="vh-spin" aria-hidden="true"></span>
        <span v-else-if="indicator === 'ok'" class="vh-check" aria-hidden="true">✓</span>
        <span v-else-if="indicator === 'dash'" class="vh-dash" aria-hidden="true">—</span>
      </span>
    </span>

    <!-- 胶囊：状态压成 10px 小字 / 图标。Pill: status shrunk to 10px text/icon. -->
    <span class="vh-pill">
      <VoiceStatusBadge :kind="statusKind" />
      <VoiceWaveform class="vh-wave" :active="micLive" :bars="32" :tone="ghost ? 'muted' : 'rgb'" />
    </span>
  </button>
</template>

<script setup lang="ts">
/**
 * 语音条（v3）：沿用原胶囊形态，仅在识别/定稿时向右扩展文本段。
 * 只展示识别过程与去向；助手回复正文只在聊天面板。
 *
 * Voice bar (v3): keeps the original pill and only extends a text segment during
 * recognition/finalisation. Shows the recognition journey only; assistant reply text
 * stays in the chat panel.
 */
import { computed } from 'vue'
import VoiceStatusBadge, { type VoiceStatusKind } from './VoiceStatusBadge.vue'
import VoiceWaveform from './VoiceWaveform.vue'
import type { AsstState } from '../../composables/useAssistant'
import type { StateVisual } from '../../composables/useAssistantVisuals'
import { liveTranscript, hudOutcome, streamError, streamPhase } from '../../composables/assistant/storeTranscript'
import { callActive } from '../../composables/assistant/store'

const props = withDefaults(defineProps<{
  state: AsstState
  visual: StateVisual
  wakeHint: string
  visible: boolean
  side: 'left' | 'right'
}>(), {})

defineEmits<{ open: [] }>()

/** 正在识别。Recognition in progress. */
const recognizing = computed(() =>
  liveTranscript.value.status === 'recognizing' || streamPhase.value === 'recognizing')
/** 已接受为 LLM 输入。Accepted as LLM input. */
const accepted = computed(() => hudOutcome.value === 'accepted')
/** 旁白。Discarded bystander text. */
const ghost = computed(() => hudOutcome.value === 'ghost')
/** 麦克风活跃（波形起伏）。Mic-live phases. */
const micLive = computed(() => [
  'listening', 'recording', 'awaiting_answer', 'standby', 'transcribing',
].includes(props.state) || recognizing.value)

/** 识别文本。Recognition text. */
const transcriptText = computed(() => {
  if (recognizing.value) return liveTranscript.value.interim
  if (accepted.value) return liveTranscript.value.finalText
  if (ghost.value) return liveTranscript.value.ghostText
  if (liveTranscript.value.status === 'finalized') return liveTranscript.value.finalText
  return ''
})

/** 是否伸出文本段。Whether to extend the text segment. */
const showBox = computed(() =>
  recognizing.value || accepted.value || ghost.value ||
  (liveTranscript.value.status === 'finalized' && !!transcriptText.value))

/** 状态徽章的 kind（每种状态独立配色/动效）。Status badge kind. */
const statusKind = computed<VoiceStatusKind>(() => {
  if (streamError.value) return 'error'
  if (accepted.value) return 'ready'
  if (ghost.value) return 'ghost'
  if (recognizing.value) return 'recognizing'
  switch (props.state) {
    case 'thinking': return 'thinking'
    case 'tool_calling': return 'tool'
    case 'responding': return 'responding'
    case 'awaiting_answer': return 'awaiting'
    default: break
  }
  if (callActive.value && ['listening', 'recording', 'standby', 'transcribing'].includes(props.state)) {
    return 'call'
  }
  switch (props.state) {
    case 'listening': return 'listening'
    case 'standby': return 'standby'
    case 'recording': return 'command'
    default: return 'idle'
  }
})

/** 文本段右侧图标。Right icon of the text segment. */
const indicator = computed(() => {
  if (streamError.value) return 'dash'
  if (accepted.value) return 'ok'
  if (ghost.value) return 'dash'
  if (recognizing.value) return 'spinner'
  return ''
})

/** 状态色。State colour. */
const hudStyle = computed(() => ({ '--vh-color': props.visual.color }))

/** 无障碍标签。Accessibility label. */
const ariaLabel = computed(() =>
  `${statusKind.value}${transcriptText.value ? '：' + transcriptText.value : ''}`)
</script>

<style scoped>
.voice-hud {
  position: relative; display: flex; align-items: center; gap: 6px;
  max-width: calc(100vw - 96px);
  background: none; border: none; padding: 0; color: var(--text-2);
  cursor: pointer; font-family: inherit;
}
.voice-hud.hidden { display: none; }

/* 胶囊：原形态，保持紧凑。Pill: the original compact shape. */
.vh-pill {
  position: relative; display: flex; align-items: center; gap: var(--sp-3);
  height: 49px; padding: 0 var(--sp-4);
  background: var(--panel-bg, rgba(15, 23, 42, .82));
  border: 1px solid var(--border-soft);
  border-radius: var(--r-full);
  backdrop-filter: blur(12px) saturate(140%);
  box-shadow: var(--shadow-2), inset 0 1px 0 rgba(255,255,255,.045);
  flex: none;
}
/* 尖角指向球。Tail points at the ball. */
.vh-pill::after {
  content: ""; position: absolute; top: 50%; width: 10px; height: 10px;
  transform: translateY(-50%) rotate(45deg);
  background: inherit; border: solid var(--border-soft);
}
.voice-hud.side-right .vh-pill::after { right: -6px; border-width: 1px 1px 0 0; }
.voice-hud.side-left .vh-pill::after { left: -6px; border-width: 0 0 1px 1px; }
.vh-wave { width: 80px; }

/* 文本段：只在有识别文本时出现，向左/右伸出。 */
.vh-box {
  display: flex; align-items: center; gap: var(--sp-2);
  height: 60px; min-width: 260px; max-width: 320px;
  padding: 7px var(--sp-3);
  background: var(--panel-bg, rgba(15, 23, 42, .82));
  border: 1px solid var(--border-soft); border-radius: var(--r-md);
  backdrop-filter: blur(12px) saturate(140%);
  box-shadow: var(--shadow-2), inset 0 1px 0 rgba(255,255,255,.045);
  animation: vh-grow .18s var(--ease-out, ease-out) both;
}
@keyframes vh-grow { from { opacity: 0; transform: translateX(4px); } to { opacity: 1; transform: none; } }
.vh-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.vh-role { font-size: 12px; color: var(--text-3); line-height: 1.1; }
.vh-text {
  font-size: var(--fs-md); color: var(--text-1); line-height: 1.4;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.vh-caret {
  display: inline-block; width: 2px; height: 14px; margin-left: 2px;
  vertical-align: -1px; background: var(--brand-c2);
  animation: vh-blink 1s steps(2, start) infinite;
}
@keyframes vh-blink { 50% { opacity: 0; } }
.vh-end { flex: none; width: 20px; display: grid; place-items: center; font-size: 14px; color: var(--brand-c2); }
.vh-spin { width: 13px; height: 13px; border-radius: 50%; border: 2px solid rgba(103,232,249,.25); border-top-color: var(--brand-c2); animation: vh-spin .8s linear infinite; }
@keyframes vh-spin { to { transform: rotate(360deg); } }
.vh-check { color: #34d399; }
.vh-dash { color: var(--text-3); }

/* 可提交：胶囊与文本段一起转绿。Ready: pill and segment turn green. */
.voice-hud.ready .vh-pill,
.voice-hud.ready .vh-box { border-color: rgba(52, 211, 153, .55); }
.voice-hud.ready .vh-text { color: #d1fae5; }
.voice-hud.ready .voice-waveform { color: #34d399; filter: drop-shadow(0 0 4px rgba(52,211,153,.30)); }
/* 旁白：虚线灰框。Ghost: dashed grey. */
.voice-hud.ghost .vh-box { border-style: dashed; border-color: var(--border-base); background: rgba(15,23,42,.45); }
.voice-hud.ghost .vh-text { color: var(--text-3); }
.voice-hud.ghost .voice-waveform { color: var(--text-3); filter: none; }
.voice-hud:hover .vh-pill { border-color: var(--brand-c2); }

@media (prefers-reduced-motion: reduce) {
  .vh-dot, .vh-caret, .vh-spin, .vh-box { animation: none; }
}
</style>
