<template>
  <Teleport to="body">
    <!-- 桌面悬浮球：无路由，独立常驻 -->
    <FloatBall
      :pos="pos"
      :state="asst.state.value"
      :visual="asst.visual.value"
      :message-dot="messageDot"
      :expanded="asst.expanded.value"
      :wake-enabled="asst.wakeEnabled.value"
      @update:pos="pos = $event"
      @click="onBallClick"
      @dblclick="asst.toggleWake()"
      @toggle-wake="asst.toggleWake()"
    />

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
          @select="openConsole"
        />
        <ChatInput :disabled="false" @send="asst.sendText" />
        <template #footer>
          <button class="open-console" @click="openConsole">查看完整记录 →</button>
        </template>
      </AssistantPanel>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import FloatBall from './components/assistant/FloatBall.vue'
import MiniPlayer from './components/assistant/MiniPlayer.vue'
import AssistantPanel from './components/assistant/AssistantPanel.vue'
import MiniHistory from './components/assistant/MiniHistory.vue'
import ChatInput from './components/assistant/ChatInput.vue'
import { useAssistant } from './composables/useAssistant'

const asst = useAssistant()

const messageDot = ref(false)
const miniDismiss = ref(false)
const pos = ref({
  x: typeof window !== 'undefined' ? window.innerWidth - 80 : 0,
  y: typeof window !== 'undefined' ? window.innerHeight - 80 : 0,
})

function openConsole() {
  // 桌面壳内后续可改为 Tauri 打开控制台窗口；当前兜底用浏览器
  window.open('/console', '_blank')
}

function onBallClick() {
  asst.expanded.value = !asst.expanded.value
  messageDot.value = false
}

const panelStyle = computed(() => ({
  right: Math.max(0, Math.min(window.innerWidth - pos.value.x - 380, window.innerWidth - 380)) + 'px',
  bottom: Math.min(window.innerHeight - pos.value.y, Math.max(0, window.innerHeight - 520)) + 'px',
}))
</script>

<style>
.open-console {
  width: 100%;
  border: none;
  border-top: 1px solid var(--border-base);
  background: transparent;
  color: var(--text-2);
  font-size: 12px;
  padding: 7px 0 8px;
  cursor: pointer;
}
.open-console:hover { color: var(--brand-c2); }
</style>
