<template>
  <Teleport to="body">
    <!-- 悬浮球按钮 -->
    <div
      class="float-trigger"
      :class="[{ active: expanded }, 'fx-' + asst.state.value]"
      :style="triggerStyle"
      @dblclick="onDblClick"
      @pointerdown="onDragStart"
      @touchstart.prevent="onTouchStart"
      @touchmove.prevent="onTouchMove"
      @touchend="onTouchEnd"
      @click="onClick"
      @contextmenu.prevent="onContextMenu"
    >
      <span class="trigger-icon">{{ iconText }}</span>
      <span v-if="!expanded && messageDot" class="new-dot"></span>
    </div>

    <!-- 迷你播放条：面板收起时实时展示聊天记录（音乐播放器样式） -->
    <Transition name="mini">
      <div
        v-if="showMini"
        class="mini-player"
        :class="{ active: isMiniActive }"
        :style="miniStyle"
        @click="expanded = true"
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
        <button class="mini-close" title="隐藏" @click.stop="miniDismiss = true">×</button>
      </div>
    </Transition>

    <!-- 悬浮窗 -->
    <Transition name="panel">
      <div
        v-if="expanded"
        class="float-panel"
        :style="panelStyle"
      >
        <!-- 拖拽手柄 -->
        <div class="panel-handle" @pointerdown="onPanelDragStart">
          <span class="handle-dots">⋮⋮</span>
          <span class="handle-title">小逻</span>
          <button class="handle-close" @click="expanded = false">✕</button>
        </div>

        <!-- 状态指示器 -->
        <div class="panel-status" :class="asst.state.value">
          <span class="status-dot" :style="{ background: asst.stateColor.value }"></span>
          <span class="status-label">{{ statusDisplay }}</span>
          <span v-if="asst.statusLine.value" class="status-line">{{ asst.statusLine.value }}</span>
          <button
            v-if="showEnableButton"
            class="status-toggle"
            @click="asst.toggleWake()"
          >
            👂 开启
          </button>
          <button
            v-else
            class="status-toggle stop"
            @click="asst.toggleWake()"
          >
            ⏹ 关闭
          </button>
        </div>

        <!-- 消息列表 -->
        <div class="panel-messages" ref="msgContainer">
          <div v-if="emptyHint" class="panel-hint" :class="asst.state.value">
            <template v-if="asst.state.value === 'listening'">
              <p class="hint-wave">{{ listeningWave }}</p>
              <p class="hint-sub">说 <strong>"小逻小逻"</strong> 唤醒我</p>
            </template>
            <template v-else-if="asst.state.value === 'recording'">
              <p class="hint-record">🔴 请说话...</p>
            </template>
            <template v-else-if="asst.state.value === 'transcribing'">
              <p class="hint-spin">⏳ 识别中...</p>
            </template>
            <template v-else>
              <p>双击右下角悬浮球或点击上方开启按钮</p>
              <p class="hint-sub">说 <strong>"小逻小逻"</strong> 唤醒我</p>
              <p class="hint-sub">你可以说："帮我查一下今天的天气"</p>
            </template>
          </div>

          <TransitionGroup name="msg">
            <div
              v-for="m in asst.messages.value"
              :key="m.id"
              class="msg-item"
              :class="m.role"
            >
              <div class="msg-bubble" :class="m.role">
                <div class="msg-text">{{ m.text }}</div>
                <!-- 工具调用 -->
                <div v-if="m.toolCalls?.length" class="msg-tools">
                  <div
                    v-for="tc in m.toolCalls"
                    :key="tc.id"
                    class="tool-tag"
                    :class="tc.status"
                    @click="toggleToolDetail(tc.id)"
                  >
                    <span class="tool-icon">{{ toolIcon(tc) }}</span>
                    <span class="tool-name">{{ toolLabel(tc) }}</span>
                    <span class="tool-status-badge">{{ tc.status }}</span>
                  </div>
                  <div v-if="expandedToolId === m.toolCalls[0]?.id" class="tool-detail">
                    <div class="tool-args">
                      <strong>参数:</strong>
                      <code>{{ JSON.stringify(m.toolCalls[0].args, null, 2) }}</code>
                    </div>
                    <div v-if="m.toolCalls[0].result" class="tool-result">
                      <strong>结果:</strong> {{ m.toolCalls[0].result }}
                    </div>
                  </div>
                </div>
              </div>
              <div class="msg-time">{{ formatTime(m.timestamp) }}</div>
            </div>
          </TransitionGroup>
        </div>

        <!-- 快捷操作 -->
        <div class="panel-actions">
          <button class="act-btn" @click="asst.clearMessages()" title="清空对话">🗑</button>
          <button class="act-btn" @click="expanded = false" title="收起">▼</button>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted, nextTick } from 'vue'
import type { AsstState, ToolCall } from '../composables/useAssistant'

const props = defineProps<{
  asst: ReturnType<typeof import('../composables/useAssistant').useAssistant>
}>()

const expanded = ref(false)
const messageDot = ref(false)
const expandedToolId = ref('')
const msgContainer = ref<HTMLDivElement>()
const waveIndex = ref(0)
const miniDismiss = ref(false)

// ── listening 波浪动画（setInterval 驱动，computed 依赖 Date.now() 不响应）──
let waveTimer: ReturnType<typeof setInterval> | null = null
function startWave() {
  stopWave()
  waveTimer = setInterval(() => { waveIndex.value = (waveIndex.value + 1) % 4 }, 200)
}
function stopWave() {
  if (waveTimer) { clearInterval(waveTimer); waveTimer = null }
}
// immediate: 组件（重）挂载时若已处于 listening 也立即启动波浪动画
watch(() => props.asst.state.value, (s) => {
  if (s === 'listening') startWave()
  else stopWave()
}, { immediate: true })

// ── 拖拽 ──
const pos = ref({ x: typeof window !== 'undefined' ? window.innerWidth - 80 : 0, y: typeof window !== 'undefined' ? window.innerHeight - 80 : 0 })
const dragging = ref(false)
const dragOffset = ref({ x: 0, y: 0 })
const clickTime = ref(0)

function onDragStart(e: PointerEvent) {
  dragOffset.value = { x: e.clientX - pos.value.x, y: e.clientY - pos.value.y }
  clickTime.value = Date.now()
  const target = e.target as HTMLElement
  target.setPointerCapture?.(e.pointerId)
  document.addEventListener('pointermove', onDragMove)
  document.addEventListener('pointerup', onDragEnd)
}

function onDragMove(e: PointerEvent) {
  if (Math.abs(e.clientX - dragOffset.value.x - pos.value.x) > 3 ||
      Math.abs(e.clientY - dragOffset.value.y - pos.value.y) > 3) {
    dragging.value = true
  }
  pos.value = {
    x: Math.max(0, Math.min(window.innerWidth - 56, e.clientX - dragOffset.value.x)),
    y: Math.max(0, Math.min(window.innerHeight - 56, e.clientY - dragOffset.value.y)),
  }
}

function onDragEnd(e: PointerEvent) {
  (e.target as HTMLElement).releasePointerCapture?.(e.pointerId)
  document.removeEventListener('pointermove', onDragMove)
  document.removeEventListener('pointerup', onDragEnd)
}

function onTouchStart(e: TouchEvent) {
  if (e.touches.length === 1) {
    const t = e.touches[0]
    dragOffset.value = { x: t.clientX - pos.value.x, y: t.clientY - pos.value.y }
    clickTime.value = Date.now()
  }
}
function onTouchMove(e: TouchEvent) {
  if (e.touches.length === 1) {
    const t = e.touches[0]
    if (Math.abs(t.clientX - dragOffset.value.x - pos.value.x) > 3 ||
        Math.abs(t.clientY - dragOffset.value.y - pos.value.y) > 3) {
      dragging.value = true
    }
    pos.value = {
      x: Math.max(0, Math.min(window.innerWidth - 56, t.clientX - dragOffset.value.x)),
      y: Math.max(0, Math.min(window.innerHeight - 56, t.clientY - dragOffset.value.y)),
    }
  }
}
function onTouchEnd() {
  // touch handled by click handler
}

function onClick() {
  if (dragging.value) { dragging.value = false; return }
  const elapsed = Date.now() - clickTime.value
  if (elapsed < 300) {
    expanded.value = !expanded.value
    messageDot.value = false
  }
}

function onDblClick() {
  props.asst.toggleWake()
  messageDot.value = false
}

function onPanelDragStart(e: PointerEvent) {
  // panel dragging handled by trigger
}

function onContextMenu() {
  //
}

// ── 工具详情切换 ──
function toggleToolDetail(id: string) {
  expandedToolId.value = expandedToolId.value === id ? '' : id
}

function toolIcon(tc: ToolCall) {
  const map: Record<string, string> = {
    chat: '💬',
  }
  return map[tc.name] || '🔧'
}

function toolLabel(tc: ToolCall) {
  const map: Record<string, string> = {
    chat: '对话',
  }
  return map[tc.name] || tc.name
}

function formatTime(ts: number) {
  const d = new Date(ts)
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

// ── 状态显示 ──
const iconText = computed(() => {
  const map: Record<AsstState, string> = {
    idle: '🤖',
    listening: '👂',
    recording: '🔴',
    transcribing: '⏳',
    thinking: '🤔',
    tool_calling: '🔧',
    responding: '💬',
    done: '✅',
    error: '❌',
  }
  return map[props.asst.state.value] || '🤖'
})

// 空消息时显示提示
const emptyHint = computed(() =>
  props.asst.messages.value.length === 0 &&
  ['idle', 'listening', 'recording', 'transcribing'].includes(props.asst.state.value)
)

// 显示"开启"按钮的状态
const showEnableButton = computed(() =>
  ['idle', 'error', 'done'].includes(props.asst.state.value)
)

const statusDisplay = computed(() => {
  if (props.asst.partialText.value && (props.asst.state.value === 'listening' || props.asst.state.value === 'recording')) {
    return props.asst.partialText.value
  }
  return props.asst.stateLabel.value
})

const listeningWave = computed(() => {
  const frames = ['👂   ', '👂 . ', '👂 ..', '👂 ...']
  return frames[waveIndex.value % 4]
})

// ── 迷你播放条（音乐播放器样式）──
const ACTIVE_STATES: AsstState[] = ['listening', 'recording', 'transcribing', 'thinking', 'tool_calling', 'responding']
const isMiniActive = computed(() => ACTIVE_STATES.includes(props.asst.state.value))

const lastMsg = computed(() =>
  props.asst.messages.value[props.asst.messages.value.length - 1] || null
)

const miniText = computed(() => {
  const p = props.asst.partialText.value
  if (p && ['recording', 'listening'].includes(props.asst.state.value)) return p
  if (lastMsg.value) return lastMsg.value.text
  return props.asst.statusLine.value || props.asst.stateLabel.value
})

const miniRole = computed(() => {
  if (!lastMsg.value) return 'AI 助手'
  if (lastMsg.value.role === 'user') return '你说'
  if (lastMsg.value.role === 'assistant') return '小逻'
  return '系统'
})

const miniLong = computed(() => miniText.value.length > 16)

const showMini = computed(() =>
  !expanded.value &&
  !miniDismiss.value &&
  (props.asst.messages.value.length > 0 || isMiniActive.value)
)

const miniStyle = computed(() => {
  const w = typeof window !== 'undefined' ? window.innerWidth : 0
  const h = typeof window !== 'undefined' ? window.innerHeight : 0
  // 默认显示在悬浮球左侧；悬浮球贴近左边缘时翻转到右侧，避免超出屏幕
  const leftSide = pos.value.x < 240
  const right = leftSide
    ? Math.max(0, w - pos.value.x - 56 - 10)
    : Math.max(0, w - pos.value.x + 10)
  const bottom = Math.max(0, h - pos.value.y - 52)
  return { right: right + 'px', bottom: bottom + 'px' }
})

// ── 消息变化时滚动到底部 ──
watch(() => props.asst.messages.value.length, () => {
  nextTick(() => {
    if (msgContainer.value) {
      msgContainer.value.scrollTop = msgContainer.value.scrollHeight
    }
  })
})

// 新消息提醒
watch(() => props.asst.messages.value.length, (n) => {
  if (!expanded.value && n > 0) {
    messageDot.value = true
  }
})

// 新消息到达时重新显示迷你播放条（保证"实时展示"）
watch(() => props.asst.messages.value[props.asst.messages.value.length - 1]?.id, () => {
  miniDismiss.value = false
})

// ── 样式 ──
const triggerStyle = computed(() => ({
  right: (typeof window !== 'undefined' ? window.innerWidth - pos.value.x - 56 : 0) + 'px',
  bottom: (typeof window !== 'undefined' ? window.innerHeight - pos.value.y - 56 : 0) + 'px',
  borderColor: props.asst.stateColor.value,
  boxShadow: `0 0 12px ${props.asst.stateColor.value}44`,
}))

const panelStyle = computed(() => ({
  right: Math.max(0, Math.min((typeof window !== 'undefined' ? window.innerWidth : 0) - pos.value.x - 380, (typeof window !== 'undefined' ? window.innerWidth : 0) - 380)) + 'px',
  bottom: Math.min((typeof window !== 'undefined' ? window.innerHeight : 0) - pos.value.y, Math.max(0, (typeof window !== 'undefined' ? window.innerHeight : 0) - 520)) + 'px',
}))

onUnmounted(() => {
  document.removeEventListener('pointermove', onDragMove)
  document.removeEventListener('pointerup', onDragEnd)
  stopWave()
})
</script>

<style scoped>
/* ── 悬浮球 ── */
.float-trigger {
  position: fixed;
  z-index: 9999;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: #1e293b;
  border: 2px solid #6b7280;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  user-select: none;
  touch-action: none;
  transition: transform 0.2s, box-shadow 0.3s;
}
.float-trigger:hover {
  transform: scale(1.08);
}
.float-trigger.active {
  transform: scale(0.95);
}
.trigger-icon {
  font-size: 24px;
  line-height: 1;
}
.new-dot {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #ef4444;
  animation: blink 1s infinite;
}
@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

/* ── 悬浮球状态特效 ── */
.float-trigger::after {
  content: '';
  position: absolute;
  inset: -6px;
  border-radius: 50%;
  border: 2px solid transparent;
  pointer-events: none;
}
.float-trigger.fx-idle {
  animation: fx-idle-breathe 3s ease-in-out infinite;
}
@keyframes fx-idle-breathe {
  0%, 100% { box-shadow: 0 0 6px rgba(107, 114, 128, .25); }
  50% { box-shadow: 0 0 18px rgba(107, 114, 128, .5); }
}
.float-trigger.fx-listening::after {
  border-color: #22c55e;
  animation: fx-radar 1.6s ease-out infinite;
}
.float-trigger.fx-recording::after {
  border-color: #ef4444;
  animation: fx-radar 1.1s ease-out infinite;
}
.float-trigger.fx-recording {
  animation: fx-shake 0.25s linear infinite;
}
.float-trigger.fx-transcribing::after {
  border-top-color: #a855f7;
  animation: fx-spin 1.1s linear infinite;
}
.float-trigger.fx-thinking::after {
  border-top-color: #f97316;
  animation: fx-spin 0.8s linear infinite;
}
.float-trigger.fx-tool_calling::after {
  border-top-color: #06b6d4;
  animation: fx-spin 0.6s linear infinite;
}
.float-trigger.fx-responding::after {
  border-color: #3b82f6;
  animation: fx-radar 1.3s ease-out infinite;
}
.float-trigger.fx-done {
  animation: fx-done-flash 0.6s ease-out;
}
.float-trigger.fx-error::after {
  border-color: #ef4444;
}
.float-trigger.fx-error {
  animation: fx-shake 0.3s linear infinite;
}
@keyframes fx-radar {
  0% { transform: scale(.75); opacity: .9; }
  100% { transform: scale(1.9); opacity: 0; }
}
@keyframes fx-spin { to { transform: rotate(360deg); } }
@keyframes fx-shake {
  0%, 100% { transform: translateX(0); }
  25% { transform: translateX(-2px); }
  75% { transform: translateX(2px); }
}
@keyframes fx-done-flash {
  0% { box-shadow: 0 0 0 0 rgba(34, 197, 94, .6); }
  100% { box-shadow: 0 0 0 22px rgba(34, 197, 94, 0); }
}

/* ── 悬浮窗 ── */
.float-panel {
  position: fixed;
  z-index: 9998;
  width: 360px;
  max-height: 520px;
  background: #1e293b;
  border-radius: 16px;
  border: 1px solid #334155;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 8px 32px rgba(0,0,0,0.4);
}

/* 拖拽手柄 */
.panel-handle {
  display: flex;
  align-items: center;
  padding: 10px 14px;
  cursor: grab;
  background: #0f172a;
  border-bottom: 1px solid #334155;
  gap: 8px;
}
.panel-handle:active { cursor: grabbing; }
.handle-dots { color: #64748b; font-size: 16px; letter-spacing: 2px; }
.handle-title { flex: 1; color: #e2e8f0; font-size: 14px; font-weight: 600; }
.handle-close {
  background: none; border: none; color: #94a3b8; cursor: pointer;
  font-size: 16px; padding: 2px 6px; border-radius: 4px;
}
.handle-close:hover { background: #334155; color: #f1f5f9; }

/* 状态栏 */
.panel-status {
  display: flex;
  align-items: center;
  padding: 8px 14px;
  gap: 8px;
  border-bottom: 1px solid #334155;
}
.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
  transition: background 0.3s;
}
.status-label {
  flex: 1;
  font-size: 13px;
  color: #cbd5e1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.status-line {
  font-size: 11px;
  color: #f97316;
  white-space: nowrap;
  animation: blink 1s infinite;
}
.status-toggle {
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 12px;
  border: 1px solid #22c55e;
  background: #22c55e20;
  color: #22c55e;
  cursor: pointer;
  white-space: nowrap;
}
.status-toggle.stop {
  border-color: #ef4444;
  background: #ef444420;
  color: #ef4444;
}

/* 消息区 */
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
  color: #64748b;
  font-size: 13px;
  padding: 40px 20px;
}
.panel-hint p { margin: 0 0 8px; }
.hint-sub { font-size: 12px; color: #475569; }
.hint-sub strong { color: #3b82f6; }
.panel-hint.listening { color: #22c55e; }
.panel-hint.recording .hint-record { color: #ef4444; font-size: 16px; animation: blink 0.8s infinite; }
.panel-hint.transcribing .hint-spin { color: #a855f7; font-size: 16px; }
@keyframes wave { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }

/* 消息气泡 */
.msg-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.msg-bubble {
  max-width: 90%;
  padding: 8px 12px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.5;
  word-break: break-word;
}
.msg-bubble.user {
  align-self: flex-end;
  background: #3b82f6;
  color: #fff;
  border-bottom-right-radius: 4px;
}
.msg-bubble.assistant {
  align-self: flex-start;
  background: #334155;
  color: #e2e8f0;
  border-bottom-left-radius: 4px;
}
.msg-bubble.system {
  align-self: center;
  background: #7f1d1d;
  color: #fca5a5;
  font-size: 12px;
  max-width: 80%;
  text-align: center;
}
.msg-time {
  font-size: 10px;
  color: #475569;
  padding: 0 4px;
}
.msg-item.user .msg-time { text-align: right; }
.msg-item.assistant .msg-time { text-align: left; }
.msg-item.system .msg-time { text-align: center; }

/* 工具调用 */
.msg-tools {
  margin-top: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.tool-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 6px;
  background: #1e293b;
  cursor: pointer;
  align-self: flex-start;
}
.tool-tag.running { border-left: 3px solid #f97316; }
.tool-tag.done { border-left: 3px solid #22c55e; }
.tool-tag.failed { border-left: 3px solid #ef4444; }
.tool-icon { font-size: 12px; }
.tool-name { color: #94a3b8; }
.tool-status-badge {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 8px;
  margin-left: 4px;
}
.tool-tag.running .tool-status-badge { background: #f9731620; color: #f97316; }
.tool-tag.done .tool-status-badge { background: #22c55e20; color: #22c55e; }
.tool-tag.failed .tool-status-badge { background: #ef444420; color: #ef4444; }

.tool-detail {
  margin-top: 4px;
  font-size: 11px;
  color: #94a3b8;
  background: #0f172a;
  padding: 6px 8px;
  border-radius: 6px;
  max-width: 100%;
  overflow: hidden;
}
.tool-detail strong { color: #cbd5e1; }
.tool-detail code {
  display: block;
  background: #1e293b;
  padding: 4px 6px;
  border-radius: 4px;
  margin-top: 2px;
  font-size: 11px;
  color: #a5b4fc;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 80px;
  overflow-y: auto;
}
.tool-result { margin-top: 4px; }

/* 快捷操作 */
.panel-actions {
  display: flex;
  justify-content: flex-end;
  gap: 4px;
  padding: 8px 14px;
  border-top: 1px solid #334155;
}
.act-btn {
  background: #334155;
  border: none;
  color: #94a3b8;
  font-size: 16px;
  padding: 4px 10px;
  border-radius: 8px;
  cursor: pointer;
}
.act-btn:hover { background: #475569; color: #e2e8f0; }

/* ── 过渡动画 ── */
.msg-enter-active { transition: all 0.3s ease; }
.msg-leave-active { transition: all 0.2s ease; }
.msg-enter-from { opacity: 0; transform: translateY(8px); }

.panel-enter-active { transition: all 0.3s ease-out; }
.panel-leave-active { transition: all 0.2s ease-in; }
.panel-enter-from, .panel-leave-to { opacity: 0; transform: translateY(12px) scale(0.96); }

/* 状态动画 — listening 呼吸灯 */
.panel-status.listening .status-dot {
  animation: breathe 1.4s ease-in-out infinite;
}
@keyframes breathe {
  0%, 100% { box-shadow: 0 0 4px #22c55e; }
  50% { box-shadow: 0 0 12px #22c55e, 0 0 20px #22c55e44; }
}
.panel-status.recording .status-dot {
  animation: blink 0.6s infinite;
}
.panel-status.thinking .status-dot,
.panel-status.tool_calling .status-dot,
.panel-status.transcribing .status-dot {
  background: transparent !important;
  border: 2px solid rgba(255, 255, 255, .15);
  border-top-color: #f97316;
  animation: dot-spin 0.8s linear infinite;
}
.panel-status.tool_calling .status-dot { border-top-color: #06b6d4; }
.panel-status.transcribing .status-dot { border-top-color: #a855f7; }
@keyframes dot-spin { to { transform: rotate(360deg); } }
/* ── 迷你播放条（音乐播放器样式）── */
.mini-player {
  position: fixed;
  z-index: 9998;
  display: flex;
  align-items: center;
  gap: 8px;
  width: 210px;
  padding: 6px 10px;
  background: rgba(15, 23, 42, .92);
  border: 1px solid #334155;
  border-radius: 12px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, .4);
  cursor: pointer;
  backdrop-filter: blur(4px);
  user-select: none;
}
.mini-player:hover { border-color: #475569; }

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
  background: #475569;
}
.mini-player.active .mini-eq span {
  background: #22c55e;
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
.mini-role { font-size: 11px; color: #64748b; line-height: 1; }
.mini-text {
  font-size: 12px;
  color: #e2e8f0;
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
  color: #64748b;
  cursor: pointer;
  font-size: 14px;
  padding: 0 2px;
  border-radius: 4px;
  flex-shrink: 0;
}
.mini-close:hover { background: #334155; color: #f1f5f9; }

.mini-enter-active, .mini-leave-active { transition: all .25s ease; }
.mini-enter-from, .mini-leave-to { opacity: 0; transform: translateX(-8px); }

/* small screen */
@media (max-width: 480px) {
  .float-panel {
    width: calc(100vw - 16px);
    right: 8px !important;
    max-height: 60vh;
  }
  .mini-player {
    width: 150px;
  }
}
</style>
