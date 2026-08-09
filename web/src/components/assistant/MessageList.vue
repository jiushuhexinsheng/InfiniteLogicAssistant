<template>
  <div class="panel-messages" ref="msgContainer">
    <div v-if="emptyHint" class="panel-hint" :class="state">
      <template v-if="state === 'listening'">
        <p class="hint-wave">{{ listeningWave }}</p>
        <p class="hint-sub">说 <strong>"{{ wakeKeyword }}"</strong> 唤醒我</p>
      </template>
      <template v-else-if="state === 'recording'">
        <p class="hint-record">🔴 请说话...</p>
      </template>
      <template v-else-if="state === 'transcribing'">
        <p class="hint-spin">⏳ 识别中...</p>
      </template>
      <template v-else>
        <p>双击右下角悬浮球或点击上方开启按钮</p>
        <p class="hint-sub">说 <strong>"{{ wakeKeyword }}"</strong> 唤醒我</p>
        <p class="hint-sub">你可以说："帮我查一下今天的天气"</p>
      </template>
    </div>

    <TransitionGroup name="msg">
      <MessageItem
        v-for="m in messages"
        :key="m.id"
        :message="m"
        :typewriter="m.role === 'assistant' && !animatedIds.has(m.id)"
        @retry="emit('retry', $event)"
        @cancel="emit('cancel', $event)"
        @typed="(id) => animatedIds.add(id)"
      />
    </TransitionGroup>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onUnmounted } from 'vue'
import MessageItem from './MessageItem.vue'
import type { AsstState, ChatMessage } from '../../composables/useAssistant'
import type { StateVisual } from '../../composables/useAssistantVisuals'

const props = defineProps<{
  messages: ChatMessage[]
  state: AsstState
  visual: StateVisual
  wakeKeyword: string
}>()

const emit = defineEmits<{ retry: [id: string]; cancel: [id: string] }>()

// 已播报流式动画的消息 id（面板重开不重播）
const animatedIds = new Set<string>()

const msgContainer = ref<HTMLDivElement>()
const waveIndex = ref(0)

// listening 波浪动画（setInterval 驱动，computed 依赖 Date.now() 不响应）
let waveTimer: ReturnType<typeof setInterval> | null = null
function startWave() {
  stopWave()
  waveTimer = setInterval(() => { waveIndex.value = (waveIndex.value + 1) % 4 }, 200)
}
function stopWave() {
  if (waveTimer) { clearInterval(waveTimer); waveTimer = null }
}
watch(() => props.state, (s) => {
  if (s === 'listening') startWave()
  else stopWave()
}, { immediate: true })

const listeningWave = computed(() => {
  const frames = ['👂   ', '👂 . ', '👂 ..', '👂 ...']
  return frames[waveIndex.value % 4]
})

const emptyHint = computed(() =>
  props.messages.length === 0 &&
  ['idle', 'listening', 'recording', 'transcribing'].includes(props.state)
)

// 消息变化时滚动到底
watch(() => props.messages.length, () => {
  nextTick(() => {
    if (msgContainer.value) msgContainer.value.scrollTop = msgContainer.value.scrollHeight
  })
})

onUnmounted(stopWave)
</script>

<style scoped>
.panel-messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px 14px;
  max-height: 300px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.panel-messages::-webkit-scrollbar { width: 4px; }
.panel-messages::-webkit-scrollbar-thumb { background: #475569; border-radius: 2px; }

.panel-hint {
  text-align: center;
  color: var(--text-3);
  font-size: 13px;
  padding: 40px 20px;
}
.panel-hint p { margin: 0 0 8px; }
.hint-sub { font-size: 12px; color: #475569; }
.hint-sub strong { color: var(--brand-c2); }
.panel-hint.listening { color: #34d399; }
.panel-hint.recording .hint-record { color: #ef4444; font-size: 16px; animation: blink 0.8s infinite; }
.panel-hint.transcribing .hint-spin { color: #c084fc; font-size: 16px; }

.msg-enter-active { transition: all 0.3s ease; }
.msg-leave-active { transition: all 0.2s ease; }
.msg-enter-from { opacity: 0; transform: translateY(8px); }
</style>
