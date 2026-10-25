<template>
  <!-- 语音 HUD：单一波形 + 识别过程文本 + 引擎/去向状态；替换原状态胶囊与迷你条。
       Voice HUD: one waveform + recognition text + engine/outcome state; replaces the
       old status pill and mini player. -->
  <button
    type="button"
    class="voice-hud"
    :class="[tone, `side-${side}`, { ready: accepted, ghost, hidden: !visible }]"
    :style="hudStyle"
    :aria-label="ariaLabel"
    @click="$emit('open')"
  >
    <VoiceWaveform class="vh-wave" :active="waveActive" />

    <span class="vh-meta">
      <span class="vh-line1">
        <span class="vh-state">{{ stateLabel }}</span>
        <span v-if="chip" class="vh-chip" :class="chipTone">{{ chip }}</span>
      </span>
      <span class="vh-text" :class="{ dim: !detailText }" :title="detailText">
        {{ detailText }}<span v-if="recognizing" class="vh-caret" aria-hidden="true"></span>
      </span>
    </span>

    <span class="vh-tail">
      <span class="vh-engine">{{ engineLabel }}</span>
      <span v-if="indicator === 'spinner'" class="vh-spinner" aria-hidden="true"></span>
      <span v-else-if="indicator === 'ok'" class="vh-check" aria-hidden="true">✓</span>
      <span v-else-if="indicator === 'err'" class="vh-err" aria-hidden="true">!</span>
      <span v-else-if="indicator === 'dash'" class="vh-dash" aria-hidden="true">—</span>
      <span v-else class="vh-dot" aria-hidden="true"></span>
    </span>
  </button>
</template>

<script setup lang="ts">
/**
 * 语音 HUD。只展示「声音 → 识别 → 是否作为 LLM 输入」的过程；助手回复正文只在聊天面板。
 * `visible=false`（面板展开）时隐藏；所有状态都保留，不因回复/播报而取消。
 *
 * Voice HUD. Shows only the sound → recognition → LLM-input journey; assistant reply
 * text lives solely in the chat panel. Hidden while the panel is expanded; every
 * phase stays visible (never cancelled during replies/playback).
 */
import { computed } from 'vue'
import VoiceWaveform from './VoiceWaveform.vue'
import { useConfig } from '../../composables/useApi'
import type { AsstState } from '../../composables/useAssistant'
import type { StateVisual } from '../../composables/useAssistantVisuals'
import { liveTranscript, hudOutcome, streamError, streamPhase } from '../../composables/assistant/storeTranscript'

const props = withDefaults(defineProps<{
  state: AsstState
  visual: StateVisual
  wakeHint: string
  visible: boolean
  side: 'left' | 'right'
}>(), {})

defineEmits<{ open: [] }>()

const app = useConfig()

/** 正在识别。Recognition in progress. */
const recognizing = computed(() =>
  liveTranscript.value.status === 'recognizing' || streamPhase.value === 'recognizing')
/** 本条定稿已被接受为 LLM 输入。The final was accepted as LLM input. */
const accepted = computed(() => hudOutcome.value === 'accepted')
/** 旁白/误识别，未进入对话。Discarded bystander text. */
const ghost = computed(() => hudOutcome.value === 'ghost')
/** 有声输入阶段（波形活跃）。Mic-live phases (waveform active). */
const waveActive = computed(() => [
  'listening', 'recording', 'awaiting_answer', 'standby', 'transcribing',
].includes(props.state) || recognizing.value)

/** 状态标题。State title. */
const stateLabel = computed(() => {
  if (streamError.value) return '语音错误'
  if (streamPhase.value === 'loading') return '正在加载本地语音引擎…'
  if (recognizing.value) return '正在识别'
  if (accepted.value) return '识别完成'
  if (ghost.value) return '未进入对话'
  switch (props.state) {
    case 'listening':
    case 'standby':
      return props.wakeHint ? `聆听中 · 说「${props.wakeHint}」` : '聆听中'
    case 'recording': return '已唤醒，请说指令…'
    case 'awaiting_answer': return '等待你的回答'
    case 'transcribing': return '正在识别'
    case 'thinking': return '正在思考'
    case 'tool_calling': return '正在调用工具'
    case 'responding': return '正在回复'
    default: return '双击开启语音'
  }
})

/** 第二行文本：只放识别内容，绝不放助手回复。Recognition text only. */
const detailText = computed(() => {
  if (streamError.value) return streamError.value
  if (recognizing.value && liveTranscript.value.interim) return liveTranscript.value.interim
  if (accepted.value || liveTranscript.value.status === 'finalized') {
    return liveTranscript.value.finalText || liveTranscript.value.ghostText
  }
  if (ghost.value) return liveTranscript.value.ghostText || '这段声音不会被发送'
  if (['listening', 'recording', 'awaiting_answer', 'standby', 'idle'].includes(props.state)) {
    return streamPhase.value === 'loading' ? '' : ''
  }
  return ''
})

/** 状态芯片。Outcome chip. */
const chip = computed(() => {
  if (accepted.value) return '已提交 → LLM'
  if (ghost.value) return '未进入对话'
  if (recognizing.value && liveTranscript.value.engine) {
    return liveTranscript.value.engine === 'local' ? '本地 ASR' : '云端 ASR'
  }
  return ''
})
const chipTone = computed(() => accepted.value ? 'green' : ghost.value ? 'gray' : '')

/** 右侧指示器。Right indicator. */
const indicator = computed(() => {
  if (streamError.value) return 'err'
  if (accepted.value) return 'ok'
  if (ghost.value) return 'dash'
  if (recognizing.value || streamPhase.value === 'loading') return 'spinner'
  return 'dot'
})

/** 引擎走向（KWS + ASR）。Engine routing. */
const engineLabel = computed(() => {
  const cfg = app.config.value as any
  const kws = cfg?.kws_mode === 'local' ? '本地 KWS'
    : cfg?.kws_mode === 'api' ? '文本 KWS'
      : cfg?.kws_mode === 'off' ? 'KWS 关' : 'KWS'
  const asr = cfg?.asr_mode === 'local' ? '本地 ASR'
    : cfg?.asr_mode === 'hybrid' ? '混合 ASR' : '云端 ASR'
  return `${kws} · ${asr}`
})

/** 主色：可提交绿、错误红、旁白灰、其余状态色。Primary tone. */
const tone = computed(() => {
  if (streamError.value) return 'err'
  if (accepted.value) return 'ok'
  if (ghost.value) return 'ghost'
  return 'live'
})

/** 状态色 CSS 变量。State colour CSS variables. */
const hudStyle = computed(() => ({
  '--vh-color': props.visual.color,
  '--vh-border': props.visual.color + '73',
}))

/** 无障碍标签。Accessibility label. */
const ariaLabel = computed(() => `${stateLabel.value}${detailText.value ? '：' + detailText.value : ''}`)
</script>

<style scoped>
.voice-hud {
  position: relative; display: flex; align-items: center; gap: var(--sp-3);
  width: 380px; min-width: 280px; max-width: calc(100vw - 96px);
  padding: var(--sp-2) var(--sp-3) var(--sp-2) var(--sp-q10);
  border-radius: var(--r-lg);
  border: 1px solid var(--vh-border, var(--border-soft));
  background: var(--panel-bg, rgba(15, 23, 42, .78));
  backdrop-filter: blur(14px) saturate(140%);
  box-shadow: var(--shadow-3);
  color: var(--text-2); text-align: left; cursor: pointer;
  transition: border-color var(--dur-base), box-shadow var(--dur-base), opacity var(--dur-base);
}
.voice-hud:hover { border-color: var(--brand-c2); }
.voice-hud.hidden { display: none; }

/* 尖角指向球。Tail points at the ball. */
.voice-hud::after {
  content: ""; position: absolute; top: 50%; width: 10px; height: 10px;
  transform: translateY(-50%) rotate(45deg);
  background: inherit; border: solid var(--vh-border, var(--border-soft));
}
.voice-hud.side-right::after { right: -6px; border-width: 1px 1px 0 0; }
.voice-hud.side-left::after { left: -6px; border-width: 0 0 1px 1px; }

.voice-hud.ok { border-color: rgba(52, 211, 153, .65); box-shadow: 0 0 0 1px rgba(52,211,153,.15), 0 0 24px rgba(52,211,153,.16), var(--shadow-3); }
.voice-hud.ghost { border-style: dashed; border-color: var(--border-base); background: rgba(15, 23, 42, .42); }
.voice-hud.err { border-color: rgba(248, 113, 113, .6); }

.vh-wave { width: 78px; }
.vh-meta { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.vh-line1 { display: flex; align-items: center; gap: var(--sp-2); min-width: 0; }
.vh-state { font-size: var(--fs-2xs); color: var(--text-3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.vh-chip {
  flex: none; font-size: var(--fs-2xs); line-height: 1.7; padding: 0 var(--sp-2);
  border-radius: var(--r-full); border: 1px solid rgba(103, 232, 249, .28); color: var(--brand-c2);
}
.vh-chip.green { border-color: rgba(52,211,153,.45); color: #34d399; background: rgba(52,211,153,.08); }
.vh-chip.gray { border-color: var(--border-base); color: var(--text-3); }
.vh-text {
  font-size: var(--fs-xs); color: var(--text-1); line-height: 1.45;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-height: 18px;
}
.vh-text.dim { color: var(--text-3); }
.voice-hud.ok .vh-text { color: #d1fae5; }
.voice-hud.ghost .vh-text { color: var(--text-3); }
.vh-caret {
  display: inline-block; width: 2px; height: 12px; margin-left: 2px;
  vertical-align: -2px; background: var(--brand-c2);
  animation: vh-blink 1s steps(2, start) infinite;
}
@keyframes vh-blink { 50% { opacity: 0; } }

.vh-tail { flex: none; display: flex; flex-direction: column; align-items: flex-end; gap: 4px; }
.vh-engine { font-size: var(--fs-2xs); color: var(--text-3); white-space: nowrap; }
.vh-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--brand-c2); box-shadow: 0 0 8px rgba(103,232,249,.8); animation: vh-pulse 1.2s ease-in-out infinite; }
@keyframes vh-pulse { 50% { opacity: .35; transform: scale(.85); } }
.vh-spinner { width: 11px; height: 11px; border-radius: 50%; border: 2px solid rgba(103,232,249,.25); border-top-color: var(--brand-c2); animation: vh-spin .8s linear infinite; }
@keyframes vh-spin { to { transform: rotate(360deg); } }
.vh-check { color: #34d399; font-size: var(--fs-xs); }
.vh-err { color: #f87171; font-size: var(--fs-xs); font-weight: 700; }
.vh-dash { color: var(--text-3); font-size: var(--fs-xs); }

@media (prefers-reduced-motion: reduce) {
  .vh-dot, .vh-spinner, .vh-caret { animation: none; }
}
</style>
