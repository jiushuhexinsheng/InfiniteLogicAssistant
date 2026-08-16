<template>
  <Transition name="mini">
    <div
      v-if="showMini"
      class="mini-player"
      :class="{ active: isMiniActive }"
      :style="miniStyle"
      @click="emit('open')"
    >
      <div class="mini-eq">
        <span v-for="n in 4" :key="n"></span>
      </div>
      <div class="mini-meta">
        <div class="mini-role">{{ miniRole }}</div>
        <div class="mini-text" :class="{ marquee: miniLong }">
          <span class="mini-content">{{ miniText }}</span>
        </div>
      </div>
      <button class="mini-close" title="隐藏" @click.stop="emit('dismiss')">×</button>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AsstState, ChatMessage } from '../../composables/useAssistant'
import type { StateVisual } from '../../composables/useAssistantVisuals'

const props = defineProps<{
  expanded: boolean
  pos: { x: number; y: number }
  state: AsstState
  visual: StateVisual
  messages: ChatMessage[]
  partialText: string
  statusLine: string
  miniDismiss: boolean
}>()

const emit = defineEmits<{ open: []; dismiss: [] }>()

const ACTIVE_STATES: AsstState[] = ['listening', 'recording', 'transcribing', 'thinking', 'tool_calling', 'responding']
const isMiniActive = computed(() => ACTIVE_STATES.includes(props.state))

const lastMsg = computed<ChatMessage | null>(() => props.messages[props.messages.length - 1] || null)

const miniText = computed(() => {
  const p = props.partialText
  if (p && ['recording', 'listening'].includes(props.state)) return p
  if (lastMsg.value) return lastMsg.value.text
  return props.statusLine || ''
})

const miniRole = computed(() => {
  if (!lastMsg.value) return 'AI 助手'
  if (lastMsg.value.role === 'user') return '你说'
  if (lastMsg.value.role === 'assistant') return '小逻'
  return '系统'
})

const miniLong = computed(() => miniText.value.length > 16)

const showMini = computed(() =>
  !props.expanded && !props.miniDismiss &&
  (props.messages.length > 0 || isMiniActive.value || props.state === 'error')
)

const miniStyle = computed(() => {
  const w = window.innerWidth
  const h = window.innerHeight
  const leftSide = props.pos.x < 240
  const right = leftSide
    ? Math.max(0, w - props.pos.x - 56 - 10)
    : Math.max(0, w - props.pos.x + 10)
  const bottom = Math.max(0, h - props.pos.y - 52)
  return { right: right + 'px', bottom: bottom + 'px' }
})
</script>

<style scoped>
.mini-player {
  position: fixed;
  z-index: 9998;
  display: flex;
  align-items: center;
  gap: 8px;
  width: 210px;
  padding: 6px 10px;
  border: 1px solid transparent;
  /* 品牌渐变描边 + 玻璃质感 */
  background:
    linear-gradient(var(--glass-bg-strong), var(--glass-bg-strong)) padding-box,
    var(--brand-grad) border-box;
  backdrop-filter: blur(12px) saturate(140%);
  -webkit-backdrop-filter: blur(12px) saturate(140%);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-3);
  cursor: pointer;
  user-select: none;
}
.mini-player:hover { border-color: transparent; opacity: .92; }

.mini-eq {
  display: flex;
  align-items: flex-end;
  gap: 2px;
  height: 16px;
  flex-shrink: 0;
}
.mini-eq span {
  width: 3px;
  height: 5px;
  border-radius: 1px;
  background: linear-gradient(180deg, var(--brand-c1), var(--brand-c3));
}
.mini-player.active .mini-eq span {
  background: var(--brand-grad);
  animation: eq 1s ease-in-out infinite;
}
.mini-eq span:nth-child(1) { animation-delay: 0s; }
.mini-eq span:nth-child(2) { animation-delay: .15s; }
.mini-eq span:nth-child(3) { animation-delay: .3s; }
.mini-eq span:nth-child(4) { animation-delay: .45s; }
@keyframes eq {
  0%, 100% { height: 4px; }
  50% { height: 14px; }
}

.mini-meta {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.mini-role { font-size: 11px; color: var(--text-3); line-height: 1; }
.mini-text {
  font-size: 12px;
  color: var(--text-1);
  line-height: 1.4;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.mini-text.marquee .mini-content {
  display: inline-block;
  padding-left: 100%;
  animation: marquee 9s linear infinite;
}
@keyframes marquee {
  0% { transform: translateX(0); }
  100% { transform: translateX(-100%); }
}
.mini-close {
  background: none;
  border: none;
  color: var(--text-3);
  cursor: pointer;
  font-size: 14px;
  padding: 0 2px;
  border-radius: 4px;
  flex-shrink: 0;
}
.mini-close:hover { background: #334155; color: var(--text-1); }
</style>
