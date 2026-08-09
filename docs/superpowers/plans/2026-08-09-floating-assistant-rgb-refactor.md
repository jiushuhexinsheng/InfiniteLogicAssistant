# FloatingAssistant RGB 重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `FloatingAssistant.vue` 拆分为 7 个原子子组件并应用品牌渐变/彩虹 RGB 视觉，同时保持行为与对外接口不变。

**Architecture:** 新增设计令牌层 `assistant.css` 与状态视觉配置 `useAssistantVisuals.ts`；`useAssistant.ts` 改为消费共享配置并新增 `visual` 输出；将原组件拆为 `FloatBall / MiniPlayer / AssistantPanel / StatusBar / MessageList / MessageItem / ActionBar`，由入口容器 `FloatingAssistant.vue` 组合。状态机 `useAssistant` 仍是唯一数据源，子组件单向收 props、发事件。

**Tech Stack:** Vue 3 `<script setup>` + TypeScript + Vite。**无前端单元测试框架**，验证门槛为 `npm run build`（vue-tsc 类型检查 + 构建）+ 浏览器冒烟。

## Global Constraints

- 对外接口不变：`App.vue` 仍 `import FloatingAssistant` 并传 `:asst`，**不得修改 App.vue**。
- `useAssistant` 对外返回接口不变，仅**新增** `visual` 字段。
- 品牌渐变 = `linear-gradient(135deg, #a5b4fc, #67e8f9, #6ee7b7)`（与 App 标题同款）。
- 彩虹渐变仅用于 `listening` / `recording`；其余状态保持品牌渐变。
- 状态识别色保留（来自 `STATE_VISUALS.color`），保证可读性。
- 行为必须保留：球体拖拽、点击展开/收起、双击唤醒、迷你条边界翻转、消息滚动到底、新消息红点、状态灯、清空/收起按钮。
- 彩虹 `hue-rotate` / 渐变动画只作用于小元素（球体、状态点、迷你 eq），不做大面 filter。
- 每个任务结束必须 `npm run build` 通过。

---

### Task 1: 设计令牌层 — `assistant.css`

**Files:**
- Create: `web/src/styles/assistant.css`
- Modify: `web/src/main.ts`

**Interfaces:**
- Produces: CSS 变量 `--brand-c1/2/3`、`--brand-grad`、`--rainbow`、`--panel-bg`、`--border-base`、`--text-1/2/3`；工具类 `.grad-text` / `.grad-border` / `.grad-glow`。

- [ ] **Step 1: 创建 `web/src/styles/assistant.css`**

```css
/* 无限逻辑·语音助手 — 悬浮助手视觉令牌与渐变工具类 */
:root {
  --brand-c1: #a5b4fc;              /* 靛 */
  --brand-c2: #67e8f9;              /* 青 */
  --brand-c3: #6ee7b7;              /* 绿 */
  --brand-grad: linear-gradient(135deg, var(--brand-c1), var(--brand-c2), var(--brand-c3));
  --rainbow: conic-gradient(from 0deg,
    #ef4444, #f97316, #eab308, #22c55e, #06b6d4, #3b82f6, #a855f7, #ef4444);
  --panel-bg: rgba(15, 23, 42, .92);
  --border-base: #334155;
  --text-1: #e2e8f0;
  --text-2: #94a3b8;
  --text-3: #64748b;
}

/* 渐变文字 */
.grad-text {
  background: var(--brand-grad);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

/* 渐变描边圆角容器（background-clip 双层技巧）。
   内填充色用 --grad-inner 覆盖；描边渐变用 --grad-border-grad 覆盖（组件切彩虹时改此变量）。 */
.grad-border {
  border: 1px solid transparent;
  background:
    linear-gradient(var(--grad-inner, #1e293b), var(--grad-inner, #1e293b)) padding-box,
    var(--grad-border-grad, var(--brand-grad)) border-box;
}

/* 品牌光晕 */
.grad-glow {
  box-shadow: 0 0 12px rgba(103, 232, 249, .25), 0 0 24px rgba(110, 231, 183, .15);
}

/* 彩虹 hue 旋转（聆听/录音专用，只作用于小元素） */
@keyframes rainbow-hue {
  from { filter: hue-rotate(0deg); }
  to   { filter: hue-rotate(360deg); }
}
```

- [ ] **Step 2: 在 `web/src/main.ts` 引入**

```ts
import { createApp } from 'vue'
import App from './App.vue'
import './styles/app.css'
import './styles/assistant.css'

createApp(App).mount('#app')
```

- [ ] **Step 3: 验证构建**

Run: `cd web && npm run build`
Expected: PASS（vue-tsc 无错误 + vite build 成功）

- [ ] **Step 4: 提交**

```bash
git add web/src/styles/assistant.css web/src/main.ts
git commit -m "feat: 新增悬浮助手设计令牌层 assistant.css"
```

---

### Task 2: 状态视觉配置 — `useAssistantVisuals.ts`

**Files:**
- Create: `web/src/composables/useAssistantVisuals.ts`

**Interfaces:**
- Consumes: `AsstState` 类型（从 `./useAssistant` 导入，type-only，无运行时循环：运行时仅 useAssistant→useAssistantVisuals 单向依赖）。
- Produces: `interface StateVisual`、`STATE_VISUALS: Record<AsstState, StateVisual>`、`resolveStateLabel(v, kw): string`。

- [ ] **Step 1: 创建文件**

```ts
import type { AsstState } from './useAssistant'

export interface StateVisual {
  icon: string
  label: string | ((kw: string) => string)
  color: string
  fx: string
  grad: 'brand' | 'rainbow'
}

export const STATE_VISUALS: Record<AsstState, StateVisual> = {
  idle:         { icon: '🤖', label: '双击唤醒',                  color: '#6b7280', fx: 'fx-idle',          grad: 'brand' },
  listening:    { icon: '👂', label: kw => `聆听中…说"${kw}"`,     color: '#34d399', fx: 'fx-listening',     grad: 'rainbow' },
  recording:    { icon: '🔴', label: '录音中…',                   color: '#f87171', fx: 'fx-recording',     grad: 'rainbow' },
  transcribing: { icon: '⏳', label: '识别中…',                   color: '#c084fc', fx: 'fx-transcribing',  grad: 'brand' },
  thinking:     { icon: '🤔', label: '思考中…',                   color: '#fb923c', fx: 'fx-thinking',      grad: 'brand' },
  tool_calling: { icon: '🔧', label: '执行中…',                   color: '#22d3ee', fx: 'fx-tool_calling',  grad: 'brand' },
  responding:   { icon: '💬', label: '',                          color: '#818cf8', fx: 'fx-responding',    grad: 'brand' },
  done:         { icon: '✅', label: '完成',                      color: '#34d399', fx: 'fx-done',          grad: 'brand' },
  error:        { icon: '❌', label: '出错了',                    color: '#f87171', fx: 'fx-error',         grad: 'brand' },
}

export function resolveStateLabel(v: StateVisual, kw: string): string {
  return typeof v.label === 'function' ? v.label(kw) : v.label
}
```

- [ ] **Step 2: 验证构建**

Run: `cd web && npm run build`
Expected: PASS（此时 useAssistant 尚未消费，仅类型检查通过）

- [ ] **Step 3: 提交**

```bash
git add web/src/composables/useAssistantVisuals.ts
git commit -m "feat: 状态视觉配置化 useAssistantVisuals.ts（STATE_VISUALS + 动态 label）"
```

---

### Task 3: `useAssistant.ts` 接入共享配置

**Files:**
- Modify: `web/src/composables/useAssistant.ts`

**Interfaces:**
- Consumes: `STATE_VISUALS`、`resolveStateLabel`、`StateVisual`（来自 useAssistantVisuals）。
- Produces: 新增返回字段 `visual: ComputedRef<StateVisual>`；`stateLabel`/`stateColor` 语义不变。

- [ ] **Step 1: 删除硬编码 map，改用共享配置**

在文件顶部 import 区域追加：

```ts
import { STATE_VISUALS, resolveStateLabel, type StateVisual } from './useAssistantVisuals'
```

把现有的 `stateLabel` / `stateColor` 两个 computed 整体替换为：

```ts
  // ── 状态视觉（数据驱动，来自 useAssistantVisuals）──
  const visual = computed<StateVisual>(() => STATE_VISUALS[state.value] || STATE_VISUALS.idle)
  const stateLabel = computed(() => resolveStateLabel(visual.value, wakeKeyword.value))
  const stateColor = computed(() => visual.value.color)
```

- [ ] **Step 2: 在 return 中新增 `visual`**

找到 `return {` 中的 `stateLabel,` 行，在其前插入 `visual,`（保持其余返回项不动）。

- [ ] **Step 3: 验证构建**

Run: `cd web && npm run build`
Expected: PASS（注意：现有 FloatingAssistant.vue 仍引用旧返回项，均保留故不报错）

- [ ] **Step 4: 提交**

```bash
git add web/src/composables/useAssistant.ts
git commit -m "refactor: useAssistant 状态视觉改用共享 STATE_VISUALS，新增 visual 输出"
```

---

### Task 4: `FloatBall.vue`（悬浮球）

**Files:**
- Create: `web/src/components/assistant/FloatBall.vue`

**Interfaces:**
- Consumes: `props { pos: {x,y}, state: AsstState, visual: StateVisual, messageDot: boolean, expanded: boolean }`
- Produces: emits `update:pos`(拖拽), `click`(单击展开), `dblclick`(双击唤醒)。

- [ ] **Step 1: 创建组件**

```vue
<template>
  <div
    class="float-trigger"
    :class="[visual.fx, visual.grad === 'rainbow' ? 'fx-rainbow' : '', { active: expanded }]"
    :style="triggerStyle"
    @pointerdown="onDragStart"
    @touchstart.prevent="onTouchStart"
    @touchmove.prevent="onTouchMove"
    @touchend="onTouchEnd"
    @click="onClick"
    @dblclick="emit('dblclick')"
  >
    <span class="trigger-icon">{{ visual.icon }}</span>
    <span v-if="!expanded && messageDot" class="new-dot"></span>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { AsstState } from '../../composables/useAssistant'
import type { StateVisual } from '../../composables/useAssistantVisuals'

const props = defineProps<{
  pos: { x: number; y: number }
  state: AsstState
  visual: StateVisual
  messageDot: boolean
  expanded: boolean
}>()

const emit = defineEmits<{
  'update:pos': [pos: { x: number; y: number }]
  click: []
  dblclick: []
}>()

const dragging = ref(false)
const dragOffset = ref({ x: 0, y: 0 })
const clickTime = ref(0)

function onDragStart(e: PointerEvent) {
  dragOffset.value = { x: e.clientX - props.pos.x, y: e.clientY - props.pos.y }
  clickTime.value = Date.now()
  const target = e.target as HTMLElement
  target.setPointerCapture?.(e.pointerId)
  document.addEventListener('pointermove', onDragMove)
  document.addEventListener('pointerup', onDragEnd)
}

function onDragMove(e: PointerEvent) {
  if (Math.abs(e.clientX - dragOffset.value.x - props.pos.x) > 3 ||
      Math.abs(e.clientY - dragOffset.value.y - props.pos.y) > 3) dragging.value = true
  emit('update:pos', {
    x: Math.max(0, Math.min(window.innerWidth - 56, e.clientX - dragOffset.value.x)),
    y: Math.max(0, Math.min(window.innerHeight - 56, e.clientY - dragOffset.value.y)),
  })
}

function onDragEnd(e: PointerEvent) {
  (e.target as HTMLElement).releasePointerCapture?.(e.pointerId)
  document.removeEventListener('pointermove', onDragMove)
  document.removeEventListener('pointerup', onDragEnd)
}

function onTouchStart(e: TouchEvent) {
  if (e.touches.length === 1) {
    const t = e.touches[0]
    dragOffset.value = { x: t.clientX - props.pos.x, y: t.clientY - props.pos.y }
    clickTime.value = Date.now()
  }
}

function onTouchMove(e: TouchEvent) {
  if (e.touches.length === 1) {
    const t = e.touches[0]
    if (Math.abs(t.clientX - dragOffset.value.x - props.pos.x) > 3 ||
        Math.abs(t.clientY - dragOffset.value.y - props.pos.y) > 3) dragging.value = true
    emit('update:pos', {
      x: Math.max(0, Math.min(window.innerWidth - 56, t.clientX - dragOffset.value.x)),
      y: Math.max(0, Math.min(window.innerHeight - 56, t.clientY - dragOffset.value.y)),
    })
  }
}

function onTouchEnd() { /* click 事件处理 */ }

function onClick() {
  if (dragging.value) { dragging.value = false; return }
  if (Date.now() - clickTime.value < 300) emit('click')
}

onUnmounted(() => {
  document.removeEventListener('pointermove', onDragMove)
  document.removeEventListener('pointerup', onDragEnd)
})

const triggerStyle = computed(() => ({
  right: (window.innerWidth - props.pos.x - 56) + 'px',
  bottom: (window.innerHeight - props.pos.y - 56) + 'px',
}))
</script>

<style scoped>
/* 迁移自原 FloatingAssistant.vue 的 .float-trigger / .trigger-icon / .new-dot / 状态特效样式 */
.float-trigger {
  position: fixed;
  z-index: 9999;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: #1e293b;
  /* 品牌渐变描边 + 慢呼吸光晕 */
  border: 1px solid transparent;
  background:
    linear-gradient(#1e293b, #1e293b) padding-box,
    var(--brand-grad) border-box;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  user-select: none;
  touch-action: none;
  transition: transform 0.2s, box-shadow 0.3s;
  animation: ball-breathe 3s ease-in-out infinite;
}
.float-trigger:hover { transform: scale(1.08); }
.float-trigger.active { transform: scale(0.95); }
@keyframes ball-breathe {
  0%, 100% { box-shadow: 0 0 8px rgba(165, 180, 252, .25); }
  50%      { box-shadow: 0 0 18px rgba(110, 231, 183, .4), 0 0 30px rgba(103, 232, 249, .2); }
}
.trigger-icon { font-size: 24px; line-height: 1; }
.new-dot {
  position: absolute;
  top: 4px; right: 4px;
  width: 10px; height: 10px;
  border-radius: 50%;
  background: #ef4444;
  animation: blink 1s infinite;
}
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }

/* 彩虹激活（listening/recording） */
.fx-rainbow {
  border-color: transparent;
  background:
    linear-gradient(#1e293b, #1e293b) padding-box,
    var(--rainbow) border-box;
  animation: ball-breathe 1.2s ease-in-out infinite, rainbow-hue 3s linear infinite;
}
</style>
```

> 注：原有 `fx-idle`（呼吸）/`fx-listening`（雷达环）/`fx-recording`（抖动）/`fx-transcribing`/`fx-thinking`/`fx-tool_calling`/`fx-responding`（雷达）/`fx-done`/`fx-error` 特效类全部迁移到此组件 `<style>`，使用 `STATE_VISUALS.color` 作为 accent 色，保留原关键帧（`fx-radar`/`fx-spin`/`fx-shake`/`fx-done-flash`）。

- [ ] **Step 2: 验证构建**

Run: `cd web && npm run build`
Expected: PASS（文件尚未被引用，仅类型检查）

- [ ] **Step 3: 提交**

```bash
git add web/src/components/assistant/FloatBall.vue
git commit -m "feat: 悬浮球子组件 FloatBall — 品牌渐变环 + 彩虹激活 + 拖拽/点击/双击"
```

---

### Task 5: `MiniPlayer.vue`（迷你播放条）

**Files:**
- Create: `web/src/components/assistant/MiniPlayer.vue`

**Interfaces:**
- Consumes: `props { expanded, pos, state, visual, messages, partialText, statusLine, miniDismiss }`（`messages: ChatMessage[]`）
- Produces: emits `open`(点击展开), `dismiss`(点 × 隐藏)。

- [ ] **Step 1: 创建组件**

```vue
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
  (props.messages.length > 0 || isMiniActive.value)
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
/* 迁移自原 .mini-player 系列样式；eq 条用品牌渐变，边框用 .grad-border 双层技巧 */
.mini-player {
  position: fixed;
  z-index: 9998;
  display: flex;
  align-items: center;
  gap: 8px;
  width: 210px;
  padding: 6px 10px;
  background: var(--panel-bg);
  border: 1px solid transparent;
  background:
    linear-gradient(var(--panel-bg), var(--panel-bg)) padding-box,
    var(--brand-grad) border-box;
  border-radius: 12px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, .4);
  cursor: pointer;
  backdrop-filter: blur(4px);
  user-select: none;
}
.mini-eq span { background: linear-gradient(180deg, var(--brand-c1), var(--brand-c3)); }
.mini-player.active .mini-eq span {
  background: var(--brand-grad);
  animation: eq 1s ease-in-out infinite;
}
/* 其余 .mini-meta/.mini-role/.mini-text/.mini-long/.mini-close/@keyframes eq 迁移自原文件 */
</style>
```

> 注：`mini-role`/`mini-text`/`mini-close`/`marquee`/`eq` 关键帧等其余样式从原 `FloatingAssistant.vue` 迁移。新消息到达时恢复迷你条（原 `watch lastMsg.id → miniDismiss=false`）由入口容器负责（见 Task 11）。

- [ ] **Step 2: 验证构建**

Run: `cd web && npm run build`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add web/src/components/assistant/MiniPlayer.vue
git commit -m "feat: 迷你播放条子组件 MiniPlayer — 品牌渐变 eq/边框 + 边界翻转"
```

---

### Task 6: `MessageItem.vue`（消息项）

**Files:**
- Create: `web/src/components/assistant/MessageItem.vue`

**Interfaces:**
- Consumes: `props { message: ChatMessage }`；`ToolCall` 类型。
- Produces: emits `toggle-tool`(可选)；内部管理 `expandedToolId`；暴露 slot `#tool-actions`。

- [ ] **Step 1: 创建组件**

```vue
<template>
  <div class="msg-item" :class="message.role">
    <div class="msg-bubble" :class="message.role">
      <div class="msg-text">{{ message.text }}</div>
      <div v-if="message.toolCalls?.length" class="msg-tools">
        <div
          v-for="tc in message.toolCalls"
          :key="tc.id"
          class="tool-tag"
          :class="tc.status"
          @click="expandedToolId = expandedToolId === tc.id ? '' : tc.id"
        >
          <span class="tool-icon">{{ toolIcon(tc) }}</span>
          <span class="tool-name">{{ toolLabel(tc) }}</span>
          <span class="tool-status-badge">{{ tc.status }}</span>
        </div>
        <div v-if="expandedToolId === message.toolCalls[0]?.id" class="tool-detail">
          <div class="tool-args">
            <strong>参数:</strong>
            <code>{{ JSON.stringify(message.toolCalls[0].args, null, 2) }}</code>
          </div>
          <div v-if="message.toolCalls[0].result" class="tool-result">
            <strong>结果:</strong> {{ message.toolCalls[0].result }}
          </div>
        </div>
        <slot name="tool-actions" :tool="message.toolCalls[0]"></slot>
      </div>
    </div>
    <div class="msg-time">{{ formatTime(message.timestamp) }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { ChatMessage, ToolCall } from '../../composables/useAssistant'

defineProps<{ message: ChatMessage }>()
const expandedToolId = ref('')

function toolIcon(tc: ToolCall) {
  const map: Record<string, string> = { chat: '💬' }
  return map[tc.name] || '🔧'
}

function toolLabel(tc: ToolCall) {
  const map: Record<string, string> = { chat: '对话' }
  return map[tc.name] || tc.name
}

function formatTime(ts: number) {
  const d = new Date(ts)
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}
</script>

<style scoped>
/* 用户气泡：品牌渐变背景；助手气泡：暗色底 + 渐变左边框 */
.msg-bubble.user {
  background: var(--brand-grad);
  color: #fff;
}
.msg-bubble.assistant {
  background: #334155;
  color: var(--text-1);
  border-left: 2px solid transparent;
  border-left-color: var(--brand-c2);
}
/* 其余 .msg-item/.msg-bubble/.msg-time/.msg-tools/.tool-tag/.tool-detail 迁移自原文件 */
</style>
```

- [ ] **Step 2: 验证构建**

Run: `cd web && npm run build`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add web/src/components/assistant/MessageItem.vue
git commit -m "feat: 消息项子组件 MessageItem — 用户气泡品牌渐变 + 助手渐变左边框 + 工具调用"
```

---

### Task 7: `MessageList.vue`（消息列表 + 空态提示）

**Files:**
- Create: `web/src/components/assistant/MessageList.vue`

**Interfaces:**
- Consumes: `props { messages: ChatMessage[], state: AsstState, visual: StateVisual, wakeKeyword: string }`
- Produces: 无事件；内部滚动到底 + 波浪动画。

- [ ] **Step 1: 创建组件**

```vue
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
      <MessageItem v-for="m in messages" :key="m.id" :message="m" />
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

const msgContainer = ref<HTMLDivElement>()
const waveIndex = ref(0)

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

watch(() => props.messages.length, () => {
  nextTick(() => {
    if (msgContainer.value) msgContainer.value.scrollTop = msgContainer.value.scrollHeight
  })
})

onUnmounted(stopWave)
</script>

<style scoped>
/* 迁移自原 .panel-messages/.panel-hint/.hint-*/.msg-enter-active 系列样式 */
</style>
```

- [ ] **Step 2: 验证构建**

Run: `cd web && npm run build`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add web/src/components/assistant/MessageList.vue web/src/components/assistant/MessageItem.vue
git commit -m "feat: 消息列表子组件 MessageList — 滚动到底 + 空态提示 + 波浪动画"
```

---

### Task 8: `StatusBar.vue`（状态栏）

**Files:**
- Create: `web/src/components/assistant/StatusBar.vue`

**Interfaces:**
- Consumes: `props { state: AsstState, visual: StateVisual, statusLine: string, partialText: string, wakeEnabled: boolean }`
- Produces: emits `toggleWake`。

- [ ] **Step 1: 创建组件**

```vue
<template>
  <div class="panel-status" :class="[state, visual.grad === 'rainbow' ? 'st-rainbow' : '']">
    <span class="status-dot" :style="{ background: visual.color, boxShadow: `0 0 8px ${visual.color}66` }"></span>
    <span class="status-label">{{ statusDisplay }}</span>
    <span v-if="statusLine" class="status-line">{{ statusLine }}</span>
    <button v-if="showEnableButton" class="status-toggle" @click="emit('toggleWake')">👂 开启</button>
    <button v-else class="status-toggle stop" @click="emit('toggleWake')">⏹ 关闭</button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AsstState } from '../../composables/useAssistant'
import type { StateVisual } from '../../composables/useAssistantVisuals'

const props = defineProps<{
  state: AsstState
  visual: StateVisual
  statusLine: string
  partialText: string
  wakeEnabled: boolean
}>()

const emit = defineEmits<{ toggleWake: [] }>()

// 保留原逻辑：聆听/录音时优先显示实时转写 partialText
const statusDisplay = computed(() => {
  if (props.partialText && (props.state === 'listening' || props.state === 'recording')) {
    return props.partialText
  }
  const label = typeof props.visual.label === 'function' ? props.visual.label('') : props.visual.label
  return label
})

const showEnableButton = computed(() =>
  ['idle', 'error', 'done'].includes(props.state)
)
</script>

<style scoped>
/* 迁移自原 .panel-status/.status-dot/.status-label/.status-line/.status-toggle 系列样式；
   呼吸/旋转/闪烁等状态动画迁移自原文件，accent 色改用 STATE_VISUALS.color */
</style>
```

- [ ] **Step 2: 验证构建**

Run: `cd web && npm run build`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add web/src/components/assistant/StatusBar.vue
git commit -m "feat: 状态栏子组件 StatusBar — 渐变状态灯 + 识别色 + 开启/关闭"
```

---

### Task 9: `ActionBar.vue`（操作栏）

**Files:**
- Create: `web/src/components/assistant/ActionBar.vue`

**Interfaces:**
- Consumes: 无 props
- Produces: emits `clear`(清空), `close`(收起)。

- [ ] **Step 1: 创建组件**

```vue
<template>
  <div class="panel-actions">
    <button class="act-btn" title="清空对话" @click="emit('clear')">🗑</button>
    <button class="act-btn" title="收起" @click="emit('close')">▼</button>
  </div>
</template>

<script setup lang="ts">
const emit = defineEmits<{ clear: []; close: [] }>()
</script>

<style scoped>
/* 迁移自原 .panel-actions/.act-btn；hover 加品牌渐变描边 */
.panel-actions {
  display: flex;
  justify-content: flex-end;
  gap: 4px;
  padding: 8px 14px;
  border-top: 1px solid var(--border-base);
}
.act-btn {
  background: #334155;
  border: 1px solid transparent;
  color: var(--text-2);
  font-size: 16px;
  padding: 4px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: all .2s;
}
.act-btn:hover {
  background: linear-gradient(#334155, #334155) padding-box, var(--brand-grad) border-box;
  color: var(--text-1);
}
</style>
```

- [ ] **Step 2: 验证构建**

Run: `cd web && npm run build`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add web/src/components/assistant/ActionBar.vue
git commit -m "feat: 操作栏子组件 ActionBar — 清空/收起 + hover 渐变"
```

---

### Task 10: `AssistantPanel.vue`（面板容器）

**Files:**
- Create: `web/src/components/assistant/AssistantPanel.vue`

**Interfaces:**
- Consumes: `props { state: AsstState, visual: StateVisual, panelStyle: object }`
- Produces: emits `close`；默认 slot 承载 StatusBar/MessageList/ActionBar；暴露 slot `#footer`。

- [ ] **Step 1: 创建组件**

```vue
<template>
  <div class="float-panel" :class="visual.grad === 'rainbow' ? 'fx-rainbow' : ''" :style="panelStyle">
    <div class="panel-handle">
      <span class="handle-dots">⋮⋮</span>
      <span class="handle-title">小逻</span>
      <button class="handle-close" @click="emit('close')">✕</button>
    </div>

    <slot></slot>

    <slot name="footer"></slot>
  </div>
</template>

<script setup lang="ts">
import type { AsstState } from '../../composables/useAssistant'
import type { StateVisual } from '../../composables/useAssistantVisuals'

defineProps<{
  state: AsstState
  visual: StateVisual
  panelStyle: Record<string, string>
}>()

const emit = defineEmits<{ close: [] }>()
</script>

<style scoped>
/* 面板骨架：品牌渐变细边框 + 深空晕染背景 */
.float-panel {
  position: fixed;
  z-index: 9998;
  width: 360px;
  max-height: 520px;
  background:
    radial-gradient(120% 60% at 50% 0%, rgba(103, 232, 249, .08), transparent 60%),
    var(--panel-bg);
  border: 1px solid transparent;
  border-image: var(--brand-grad) 1;         /* 渐变描边 */
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 8px 32px rgba(0, 0, 0, .4);
}
.float-panel.fx-rainbow {
  border-image: var(--rainbow) 1;
  animation: rainbow-hue 4s linear infinite;
}
.panel-handle {
  display: flex;
  align-items: center;
  padding: 10px 14px;
  cursor: grab;
  background: #0f172a;
  border-bottom: 1px solid var(--border-base);
  gap: 8px;
}
.handle-dots { color: var(--text-3); font-size: 16px; letter-spacing: 2px; }
.handle-title { flex: 1; color: var(--text-1); font-size: 14px; font-weight: 600; }
.handle-close {
  background: none; border: none; color: var(--text-2); cursor: pointer;
  font-size: 16px; padding: 2px 6px; border-radius: 4px;
}
.handle-close:hover { background: #334155; color: var(--text-1); }

/* 移动端 */
@media (max-width: 480px) {
  .float-panel {
    width: calc(100vw - 16px);
    right: 8px !important;
    max-height: 60vh;
  }
}
</style>
```

> 注：`border-image` 在 Safari/部分浏览器对 border-radius 支持不佳（圆角失效）。如需保证圆角，用 `background-clip` 双层技巧替代：`background: linear-gradient(var(--panel-bg), var(--panel-bg)) padding-box, var(--brand-grad) border-box;`（与 FloatBall 同法）。本实现采用后者以保证圆角。

- [ ] **Step 2: 验证构建**

Run: `cd web && npm run build`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add web/src/components/assistant/AssistantPanel.vue
git commit -m "feat: 面板容器子组件 AssistantPanel — 渐变边框 + 深空晕染 + 拖拽手柄"
```

---

### Task 11: 入口容器 `FloatingAssistant.vue` 重写

**Files:**
- Modify: `web/src/components/FloatingAssistant.vue`（整体重写）
- Delete: 原文件中已迁移到子组件的模板/CSS/逻辑

**Interfaces:**
- Consumes: `props { asst }`（`useAssistant` 返回值，新增了 `visual`）；子组件全部。
- Produces: 对外仍是 `FloatingAssistant`，供 App.vue 使用。

- [ ] **Step 1: 重写模板与逻辑**

```vue
<template>
  <Teleport to="body">
    <FloatBall
      :pos="pos"
      :state="asst.state.value"
      :visual="asst.visual.value"
      :message-dot="messageDot"
      :expanded="expanded"
      @update:pos="pos = $event"
      @click="onBallClick"
      @dblclick="onBallDblClick"
    />

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

    <Transition name="panel">
      <AssistantPanel
        v-if="expanded"
        :state="asst.state.value"
        :visual="asst.visual.value"
        :panel-style="panelStyle"
        @close="expanded = false"
      >
        <StatusBar
          :state="asst.state.value"
          :visual="asst.visual.value"
          :status-line="asst.statusLine.value"
          :partial-text="asst.partialText.value"
          :wake-enabled="asst.wakeEnabled.value"
          @toggle-wake="asst.toggleWake()"
        />
        <MessageList
          :messages="asst.messages.value"
          :state="asst.state.value"
          :visual="asst.visual.value"
          :wake-keyword="asst.wakeKeyword.value"
        />
        <ActionBar @clear="asst.clearMessages()" @close="expanded = false" />
      </AssistantPanel>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import FloatBall from './assistant/FloatBall.vue'
import MiniPlayer from './assistant/MiniPlayer.vue'
import AssistantPanel from './assistant/AssistantPanel.vue'
import StatusBar from './assistant/StatusBar.vue'
import MessageList from './assistant/MessageList.vue'
import ActionBar from './assistant/ActionBar.vue'

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

// 新消息红点
watch(() => props.asst.messages.value.length, (n) => {
  if (!expanded.value && n > 0) messageDot.value = true
})

// 新消息到达时恢复迷你条显示
watch(() => props.asst.messages.value[props.asst.messages.value.length - 1]?.id, () => {
  miniDismiss.value = false
})

const panelStyle = computed(() => ({
  right: Math.max(0, Math.min(window.innerWidth - pos.value.x - 380, window.innerWidth - 380)) + 'px',
  bottom: Math.min(window.innerHeight - pos.value.y, Math.max(0, window.innerHeight - 520)) + 'px',
}))
</script>

<style scoped>
/* 面板/迷你条过渡动画迁移自原文件 */
.panel-enter-active { transition: all 0.3s ease-out; }
.panel-leave-active { transition: all 0.2s ease-in; }
.panel-enter-from, .panel-leave-to { opacity: 0; transform: translateY(12px) scale(0.96); }
.mini-enter-active, .mini-leave-active { transition: all .25s ease; }
.mini-enter-from, .mini-leave-to { opacity: 0; transform: translateX(-8px); }
</style>
```

- [ ] **Step 2: 验证构建**

Run: `cd web && npm run build`
Expected: PASS。若 vue-tsc 报 `asst.visual` 不存在，说明 Task 3 的 return 未加 `visual`——回 Task 3 补上。

- [ ] **Step 3: 提交**

```bash
git add web/src/components/FloatingAssistant.vue
git commit -m "refactor: FloatingAssistant 重写为子组件组合容器（行为不变）"
```

---

### Task 12: 最终验证与清理

**Files:**
- 无新增；确认无残留死代码。

- [ ] **Step 1: 全库 grep 确认无遗留**

Run: `grep -rn "float-trigger\|panel-messages\|mini-player" web/src/components/FloatingAssistant.vue`
Expected: 上述类名已从入口容器移除（只存在于子组件），入口仅保留过渡动画类。

- [ ] **Step 2: 完整构建**

Run: `cd web && npm run build`
Expected: PASS

- [ ] **Step 3: 浏览器冒烟**

Run: `python main.py serve`（或 `cd web && npm run dev`），打开页面，逐一验证：
1. 悬浮球显示品牌渐变环 + 慢呼吸光晕；拖拽正常、点击展开/收起、双击触发唤醒
2. 聆听/录音时球体切彩虹循环
3. 迷你播放条显示聊天实时预览，eq 渐变，边界翻转正常，点 × 可隐藏、新消息恢复
4. 面板：渐变边框 + 深空晕染背景；状态灯/标签/开启按钮正常；消息滚动到底
5. 用户气泡品牌渐变背景、助手气泡渐变左边框；工具调用标签与详情展开正常
6. 清空/收起按钮正常

- [ ] **Step 4: 提交（如有剩余调整）**

```bash
git add -A
git commit -m "refactor: 收尾清理与验证"
```

---

## Self-Review

**Spec coverage:**
- 文件结构（7 子组件 + 入口 + 令牌 + 配置）：Task 1-11 ✓
- 状态视觉配置化 + 新增 visual 输出：Task 2-3 ✓
- 品牌渐变 / 彩虹切换（球体、面板、迷你条、状态灯、气泡/按钮）：Task 4/5/6/8/10 ✓
- Slot 扩展点：AssistantPanel `#footer`、MessageItem `#tool-actions`：Task 6/10 ✓
- 行为不变（拖拽/双击/迷你条翻转/滚动/红点）：Task 4/5/7/11 ✓
- 对外接口不变（App.vue 不改、useAssistant 接口保留）：Global Constraints + Task 3 ✓

**Placeholder scan:** 无 TBD/TODO；CSS 迁移以类名清单 + 明确说明给出（原文件即代码来源）。

**Type consistency:** `AsstState`/`StateVisual`/`ChatMessage`/`ToolCall` 均在 Task 2/useAssistant 定义；`visual.grad` 在 STATE_VISUALS 与子组件消费处一致；事件名 `update:pos`/`toggle-wake`/`clear`/`close`/`open`/`dismiss` 在 Task 4-11 间一致。
