<template>
  <Teleport to="body">
    <!-- 悬浮球（多层：图标 + 状态环 + mic 语音开关徽章） -->
    <FloatBall
      :pos="pos"
      :state="asst.state.value"
      :visual="asst.visual.value"
      :message-dot="messageDot"
      :expanded="expanded"
      :wake-enabled="asst.wakeEnabled.value"
      @update:pos="pos = $event"
      @click="onBallClick"
      @dblclick="onBallDblClick"
      @toggle-wake="asst.toggleWake()"
    />

    <!-- 迷你播放条：面板收起时实时展示聊天记录 -->
    <MiniPlayer
      :expanded="expanded"
      :pos="pos"
      :state="asst.state.value"
      :visual="asst.visual.value"
      :messages="asst.messages.value"
      :partial-text="asst.partialText.value"
      :status-line="asst.statusLine.value"
      :mini-dismiss="miniDismiss"
      @open="expanded = true"
      @dismiss="miniDismiss = true"
    />

    <!-- 悬浮窗（三段式：顶栏 / 消息区 / 输入栏） -->
    <Transition name="panel">
      <AssistantPanel
        v-if="expanded"
        :state="asst.state.value"
        :visual="asst.visual.value"
        :panel-style="panelStyle"
        :wake-keyword="asst.wakeKeyword.value"
        @clear="asst.clearMessages()"
        @close="expanded = false"
      >
        <MessageList
          :messages="asst.messages.value"
          :state="asst.state.value"
          :visual="asst.visual.value"
          :wake-keyword="asst.wakeKeyword.value"
          @retry="asst.retryTool($event)"
          @cancel="asst.cancelTool($event)"
        />
        <ChatInput :disabled="false" @send="onInputSend" />
      </AssistantPanel>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import FloatBall from './assistant/FloatBall.vue'
import MiniPlayer from './assistant/MiniPlayer.vue'
import AssistantPanel from './assistant/AssistantPanel.vue'
import MessageList from './assistant/MessageList.vue'
import ChatInput from './assistant/ChatInput.vue'

const props = defineProps<{
  asst: ReturnType<typeof import('../composables/useAssistant').useAssistant>
}>()

const expanded = ref(false)
const messageDot = ref(false)
const miniDismiss = ref(false)
const pos = ref({
  x: typeof window !== 'undefined' ? window.innerWidth - 80 : 0,
  y: typeof window !== 'undefined' ? window.innerHeight - 80 : 0,
})

function onBallClick() {
  expanded.value = !expanded.value
  messageDot.value = false
}

function onBallDblClick() {
  props.asst.toggleWake()
  messageDot.value = false
}

// 文字输入发送 → 复用 LLM 管线
function onInputSend(text: string) {
  props.asst.sendText(text)
}

// 新消息红点
watch(() => props.asst.messages.value.length, (n) => {
  if (!expanded.value && n > 0) messageDot.value = true
})

// 新消息到达时重新显示迷你播放条
watch(() => props.asst.messages.value[props.asst.messages.value.length - 1]?.id, () => {
  miniDismiss.value = false
})

const panelStyle = computed(() => ({
  right: Math.max(0, Math.min(window.innerWidth - pos.value.x - 380, window.innerWidth - 380)) + 'px',
  bottom: Math.min(window.innerHeight - pos.value.y, Math.max(0, window.innerHeight - 520)) + 'px',
}))
</script>

<style scoped>
/* 面板过渡动画 */
.panel-enter-active { transition: all 0.3s ease-out; }
.panel-leave-active { transition: all 0.2s ease-in; }
.panel-enter-from, .panel-leave-to { opacity: 0; transform: translateY(12px) scale(0.96); }

/* 迷你条过渡动画 */
.mini-enter-active, .mini-leave-active { transition: all .25s ease; }
.mini-enter-from, .mini-leave-to { opacity: 0; transform: translateX(-8px); }
</style>
