<template>
  <Teleport to="body">
    <!-- 悬浮球（多层：图标 + 状态环 + mic 语音开关徽章） -->
    <FloatBall
      :pos="pos"
      :state="asst.state.value"
      :visual="asst.visual.value"
      :message-dot="messageDot"
      :expanded="asst.expanded.value"
      :wake-enabled="asst.wakeEnabled.value"
      @update:pos="pos = $event"
      @click="onBallClick"
      @dblclick="onBallDblClick"
      @toggle-wake="asst.toggleWake()"
    />

    <!-- 迷你播放条：面板收起时实时展示当前/最近一条信息 -->
    <MiniPlayer
      :expanded="asst.expanded.value"
      :pos="pos"
      :state="asst.state.value"
      :visual="asst.visual.value"
      :messages="asst.messages.value"
      :partial-text="asst.partialText.value"
      :status-line="asst.statusLine.value"
      :mini-dismiss="miniDismiss"
      @open="asst.expanded.value = true"
      @dismiss="miniDismiss = true"
    />

    <!-- 迷你面板：简约历史（输入 + 摘要 + 工具徽章）+ 输入框 -->
    <Transition name="panel">
      <AssistantPanel
        v-if="asst.expanded.value"
        :state="asst.state.value"
        :visual="asst.visual.value"
        :panel-style="panelStyle"
        :wake-keyword="asst.wakeKeyword.value"
        @clear="asst.clearMessages()"
        @close="asst.expanded.value = false"
      >
        <MiniHistory
          :messages="asst.messages.value"
          :state="asst.state.value"
          :visual="asst.visual.value"
          :wake-keyword="asst.wakeKeyword.value"
          @select="goConsole"
        />
        <ChatInput :disabled="false" @send="onInputSend" />
        <template #footer>
          <button class="open-console" @click="goConsole">查看完整记录 →</button>
        </template>
      </AssistantPanel>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import FloatBall from './assistant/FloatBall.vue'
import MiniPlayer from './assistant/MiniPlayer.vue'
import AssistantPanel from './assistant/AssistantPanel.vue'
import MiniHistory from './assistant/MiniHistory.vue'
import ChatInput from './assistant/ChatInput.vue'

const props = defineProps<{
  asst: ReturnType<typeof import('../composables/useAssistant').useAssistant>
}>()

const router = useRouter()
const route = useRoute()

const messageDot = ref(false)
const miniDismiss = ref(false)
const pos = ref({
  x: typeof window !== 'undefined' ? window.innerWidth - 80 : 0,
  y: typeof window !== 'undefined' ? window.innerHeight - 80 : 0,
})

// 跳到完整控制台
function goConsole() {
  router.push('/console')
}

function onBallClick() {
  props.asst.expanded.value = !props.asst.expanded.value
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

// 跨路由时自动收起迷你面板，避免遮挡控制台内容
watch(() => route.fullPath, () => {
  props.asst.expanded.value = false
})

// 新消息红点
watch(() => props.asst.messages.value.length, (n) => {
  if (!props.asst.expanded.value && n > 0) messageDot.value = true
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

/* 面板 footer：查看完整记录 */
.open-console {
  width: 100%;
  border: none;
  border-top: 1px solid var(--border-base);
  background: transparent;
  color: var(--text-2);
  font-size: 12px;
  padding: 7px 0 8px;
  cursor: pointer;
  transition: color .15s, background .15s;
}
.open-console:hover { color: var(--brand-c2); background: rgba(103, 232, 249, .05); }
</style>
