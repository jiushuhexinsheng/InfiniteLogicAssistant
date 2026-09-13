<template>
  <!-- 过渡动画容器。Transition animation container. -->
  <Transition name="mini">
    <!-- 迷你播放器：悬浮球收起时显示，展示最新对话摘要。Mini player: shown when floating ball is collapsed, displays latest conversation summary. -->
    <div
      v-if="showMini"
      class="mini-player"
      :class="{ active: isMiniActive }"
      :style="miniStyle"
      @click="emit('open')"
    >
      <!-- 音频均衡器动画。Audio equalizer animation. -->
      <div class="mini-eq">
        <span v-for="n in 4" :key="n"></span>
      </div>
      <div class="mini-meta">
        <!-- 角色名（你说/衍衡/系统）。Role name (You/YanHeng/System). -->
        <div class="mini-role">{{ miniRole }}</div>
        <!-- 消息文本（超长时跑马灯）。Message text (marquee when too long). -->
        <div class="mini-text" :class="{ marquee: miniLong }">
          <span class="mini-content">{{ miniText }}</span>
        </div>
      </div>
      <!-- 隐藏按钮。Dismiss button. -->
      <button class="mini-close" title="隐藏" @click.stop="emit('dismiss')">×</button>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AsstState, ChatMessage } from '../../composables/useAssistant'
import type { StateVisual } from '../../composables/useAssistantVisuals'

/**
 * 组件属性定义。Component props definition.
 * @property expanded - 主面板是否已展开。Whether the main panel is expanded.
 * @property pos - 悬浮球在视口中的坐标。Position of the floating ball in viewport.
 * @property state - 助手当前状态。Current assistant state.
 * @property visual - 状态对应的视觉配置。Visual configuration for the current state.
 * @property messages - 聊天消息列表。Chat message list.
 * @property partialText - 录音/识别中的部分文本。Partial text during recording/transcribing.
 * @property statusLine - 状态行文本。Status line text.
 * @property miniDismiss - 迷你播放器是否已被用户隐藏。Whether mini player has been dismissed by user.
 */
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

/**
 * 组件事件定义。Component events definition.
 * @event open - 点击迷你播放器展开主面板。Click mini player to expand main panel.
 * @event dismiss - 用户隐藏迷你播放器。User dismisses mini player.
 */
const emit = defineEmits<{ open: []; dismiss: [] }>()

/** 处于活跃状态的助手状态列表。List of active assistant states. */
const ACTIVE_STATES: AsstState[] = ['listening', 'recording', 'awaiting_answer', 'transcribing', 'thinking', 'tool_calling', 'responding']

/**
 * 计算当前是否为活跃状态（控制 EQ 动画）。
 * Compute whether current state is active (controls EQ animation).
 */
const isMiniActive = computed(() => ACTIVE_STATES.includes(props.state))

/** 获取最后一条消息。Get the last message. */
const lastMsg = computed<ChatMessage | null>(() => props.messages[props.messages.length - 1] || null)

/**
 * 计算迷你播放器显示文本：优先显示录音中的部分文本，否则显示最后一条消息。
 * Compute mini player display text: prioritize partial text during recording, otherwise show last message.
 */
const miniText = computed(() => {
  const p = props.partialText
  if (p && ['recording', 'listening', 'awaiting_answer'].includes(props.state)) return p
  if (lastMsg.value) return lastMsg.value.text
  return props.statusLine || ''
})

/**
 * 计算迷你播放器角色名。Compute mini player role name.
 */
const miniRole = computed(() => {
  if (!lastMsg.value) return 'AI 助手'
  if (lastMsg.value.role === 'user') return '你说'
  if (lastMsg.value.role === 'assistant') return '衍衡'
  return '系统'
})

/** 文本是否过长需要跑马灯效果。Whether text is too long and needs marquee effect. */
const miniLong = computed(() => miniText.value.length > 16)

/**
 * 计算迷你播放器是否显示：主面板未展开、未被隐藏、且有内容或处于活跃/错误状态。
 * Compute whether mini player should show: panel not expanded, not dismissed, and has content or is active/error.
 */
const showMini = computed(() =>
  !props.expanded && !props.miniDismiss &&
  (props.messages.length > 0 || isMiniActive.value || props.state === 'error')
)

/**
 * 计算迷你播放器定位样式，根据悬浮球位置决定左右侧。
 * Compute mini player positioning style, determining left/right side based on ball position.
 */
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
/* 迷你播放器主体。Mini player main container. */
.mini-player {
  position: fixed;
  z-index: 9998;
  display: flex;
  align-items: center;
  gap: 8px;
  width: 210px;
  padding: 6px 10px;
  border: 1px solid transparent;
  /* 品牌渐变描边 + 玻璃质感。Brand gradient border + glass effect. */
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

/* 音频均衡器。Audio equalizer. */
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
/* 活跃状态时 EQ 播放动画。EQ animation when active. */
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

/* 元信息区域。Meta info area. */
.mini-meta {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.mini-role { font-size: 11px; color: var(--text-3); line-height: 1; }
/* 消息文本（单行截断）。Message text (single line truncation). */
.mini-text {
  font-size: 12px;
  color: var(--text-1);
  line-height: 1.4;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
/* 跑马灯效果（文本超长时）。Marquee effect (when text is too long). */
.mini-text.marquee .mini-content {
  display: inline-block;
  padding-left: 100%;
  animation: marquee 9s linear infinite;
}
@keyframes marquee {
  0% { transform: translateX(0); }
  100% { transform: translateX(-100%); }
}
/* 隐藏按钮。Dismiss button. */
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
