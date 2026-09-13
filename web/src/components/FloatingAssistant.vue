<template>
  <Teleport to="body">
    <!-- 漂浮单元：状态胶囊 + 迷你条 + 悬浮球同处一个容器，行方向由球所在的半边决定。
         间距交给 flex，球的位置只由 pos 决定，不看两个同伴的宽度。
         Floating dock: status pill, mini bar and ball share one container whose row direction
         follows the half the ball sits in. Flex owns the gaps, so the ball's position depends
         only on `pos`, never on how wide its neighbours are. -->
    <div class="asst-dock" :class="`ball-${ballSide}`" :style="dockStyle">
      <!-- 迷你播放条：面板收起时实时展示当前/最近一条信息。Mini player bar: shows current/latest message in real time when panel is collapsed -->
      <MiniPlayer
        :expanded="asst.expanded.value"
        :state="asst.state.value"
        :visual="asst.visual.value"
        :messages="asst.messages.value"
        :partial-text="asst.partialText.value"
        :status-line="asst.statusLine.value"
        :mini-dismiss="miniDismiss"
        @open="asst.expanded.value = true"
        @dismiss="miniDismiss = true"
      />

      <!-- 状态胶囊：把「双击唤醒 / 聆听中…」带到球边上，面板展开时淡出让位。
           Status pill: carries copy such as "双击唤醒 / 聆听中…" beside the ball, fading out
           while the panel is expanded. -->
      <StatusPill
        :visual="asst.visual.value"
        :state="asst.state.value"
        :wake-hint="asst.wakeHint.value"
        :visible="!asst.expanded.value"
        :side="ballSide"
      />

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
    </div>

    <!-- 迷你面板：简约历史（输入 + 摘要 + 工具徽章）+ 输入框。Mini panel: simplified history (input + summary + tool badges) + input field -->
    <Transition name="panel">
      <AssistantPanel
        v-if="asst.expanded.value"
        :state="asst.state.value"
        :visual="asst.visual.value"
        :panel-style="panelStyle"
        :wake-hint="asst.wakeHint.value"
        @clear="asst.clearMessages()"
        @close="asst.expanded.value = false"
      >
        <MiniHistory
          :messages="asst.messages.value"
          :state="asst.state.value"
          :visual="asst.visual.value"
          :wake-hint="asst.wakeHint.value"
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
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import FloatBall from './assistant/FloatBall.vue'
import MiniPlayer from './assistant/MiniPlayer.vue'
import StatusPill from './assistant/StatusPill.vue'
import AssistantPanel from './assistant/AssistantPanel.vue'
import MiniHistory from './assistant/MiniHistory.vue'
import ChatInput from './assistant/ChatInput.vue'
import { ballSide as ballSideAt, dockStyle as dockStyleAt } from '../composables/assistant/dockLayout'

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

/** 视口尺寸，跟随窗口变化：漂浮容器与面板都按它定位，缩窗后不会停在旧坐标。
 *  Viewport size, kept in sync with the window: the dock and the panel are positioned from it,
 *  so resizing the window does not leave them at stale coordinates. */
const viewport = ref({
  w: typeof window !== 'undefined' ? window.innerWidth : 0,
  h: typeof window !== 'undefined' ? window.innerHeight : 0,
})

// 窗口尺寸变化 → 重新计算定位。Window resize → recompute placement.
function onResize() {
  viewport.value = { w: window.innerWidth, h: window.innerHeight }
}
onMounted(() => window.addEventListener('resize', onResize))
onUnmounted(() => window.removeEventListener('resize', onResize))

/** 球所在的半边：胶囊与迷你条挂在球的内侧，贴边时不会被裁掉。
 *  The half the ball sits in; the pill and mini bar hang on its inner side so nothing is clipped. */
const ballSide = computed(() => ballSideAt(pos.value, viewport.value))

/** 漂浮容器的定位样式。Dock positioning style. */
const dockStyle = computed(() => dockStyleAt(pos.value, viewport.value))

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
  right: Math.max(0, Math.min(viewport.value.w - pos.value.x - 380, viewport.value.w - 380)) + 'px',
  bottom: Math.min(viewport.value.h - pos.value.y, Math.max(0, viewport.value.h - 520)) + 'px',
}))
</script>

<style scoped>
/* 漂浮容器：球的位置由 pos 决定，胶囊与迷你条挂在球的内侧。
   容器本身不吃鼠标事件（否则整条空白区域都会挡住页面），只有子元素收事件。
   The dock: the ball's spot comes from `pos`, with the pill and mini bar on its inner side.
   The container itself ignores pointer events (an invisible strip must not cover the page);
   only its children receive them. */
.asst-dock {
  position: fixed;
  z-index: 9999;
  display: flex;
  align-items: center;
  gap: 8px;
  pointer-events: none;
}
.asst-dock > * { pointer-events: auto; }
/* 球在左半边时整体反向：DOM 顺序是 [迷你条][胶囊][球]，反向排即球在最左、同伴依次向右。 */
.asst-dock.ball-left { flex-direction: row-reverse; }

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
