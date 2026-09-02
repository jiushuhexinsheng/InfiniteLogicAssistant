<template>
  <Teleport to="body">
    <!-- 悬浮球（多层：图标 + 状态环 + mic 语音开关徽章）。Floating ball (multi-layer: icon + status ring + mic voice toggle badge) -->
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

    <!-- 迷你播放条：面板收起时实时展示当前/最近一条信息。Mini player bar: shows current/latest message in real time when panel is collapsed -->
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

    <!-- 迷你面板：简约历史（输入 + 摘要 + 工具徽章）+ 输入框。Mini panel: simplified history (input + summary + tool badges) + input field -->
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
          <!-- 查看完整记录。View full history -->
        </template>
      </AssistantPanel>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
/**
 * 悬浮助手主组件，负责协调浮球、迷你播放条、助手面板等子组件。
 * Main floating assistant component that coordinates the float ball, mini player bar, and assistant panel.
 */
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import FloatBall from './assistant/FloatBall.vue'
import MiniPlayer from './assistant/MiniPlayer.vue'
import AssistantPanel from './assistant/AssistantPanel.vue'
import MiniHistory from './assistant/MiniHistory.vue'
import ChatInput from './assistant/ChatInput.vue'

/** 组件属性：接收 useAssistant 组合式函数的返回实例。Props: receives the useAssistant composable instance. */
const props = defineProps<{
  asst: ReturnType<typeof import('../composables/useAssistant').useAssistant>
}>()

const router = useRouter()
const route = useRoute()

/** 新消息红点标记。New message dot indicator. */
const messageDot = ref(false)
/** 迷你播放条是否已关闭。Whether the mini player bar has been dismissed. */
const miniDismiss = ref(false)
/** 悬浮球当前位置（像素坐标）。Current position of the floating ball (pixel coordinates). */
const pos = ref({
  x: typeof window !== 'undefined' ? window.innerWidth - 80 : 0,
  y: typeof window !== 'undefined' ? window.innerHeight - 80 : 0,
})

// 跳到完整控制台。Navigate to the full console.
function goConsole() {
  router.push('/console')
}

/** 点击悬浮球：展开/收起面板。Click float ball: toggle panel expand/collapse. */
function onBallClick() {
  props.asst.expanded.value = !props.asst.expanded.value
  messageDot.value = false
}

/** 双击悬浮球：切换语音唤醒。Double-click float ball: toggle voice wake. */
function onBallDblClick() {
  props.asst.toggleWake()
  messageDot.value = false
}

// 文字输入发送 → 复用 LLM 管线。Text input send → reuse LLM pipeline.
function onInputSend(text: string) {
  props.asst.sendText(text)
}

// 跨路由时自动收起迷你面板，避免遮挡控制台内容。Auto-collapse mini panel on route change to avoid blocking console content.
watch(() => route.fullPath, () => {
  props.asst.expanded.value = false
})

// 新消息红点。New message dot indicator.
watch(() => props.asst.messages.value.length, (n) => {
  if (!props.asst.expanded.value && n > 0) messageDot.value = true
})

// 新消息到达时重新显示迷你播放条。Re-show mini player bar when a new message arrives.
watch(() => props.asst.messages.value[props.asst.messages.value.length - 1]?.id, () => {
  miniDismiss.value = false
})

/** 根据悬浮球位置计算面板定位样式。Calculate panel position style based on float ball position. */
const panelStyle = computed(() => ({
  right: Math.max(0, Math.min(window.innerWidth - pos.value.x - 380, window.innerWidth - 380)) + 'px',
  bottom: Math.min(window.innerHeight - pos.value.y, Math.max(0, window.innerHeight - 520)) + 'px',
}))
</script>

<style scoped>
/* 面板过渡动画。Panel transition animation. */
.panel-enter-active { transition: all 0.3s ease-out; }
.panel-leave-active { transition: all 0.2s ease-in; }
.panel-enter-from, .panel-leave-to { opacity: 0; transform: translateY(12px) scale(0.96); }

/* 迷你条过渡动画。Mini bar transition animation. */
.mini-enter-active, .mini-leave-active { transition: all .25s ease; }
.mini-enter-from, .mini-leave-to { opacity: 0; transform: translateX(-8px); }

/* 面板 footer：查看完整记录。Panel footer: view full history. */
.open-console {
  width: 100%;
  border: none;
  border-top: 1px solid var(--border-base);
  background: transparent;
  color: var(--text-2);
  font-size: 12px;
  padding: 8px 0 9px;
  cursor: pointer;
  transition: color .15s, background .15s;
}
.open-console:hover { color: var(--brand-c2); background: rgba(103, 232, 249, .06); }
</style>
