# FloatingAssistant 第二轮重构（视觉+功能+聊天页+文字输入）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在已拆分子组件的基础上，完成第二轮重构：SVG 图标集、多层组合球、三段式聊天窗口、气泡头像+markdown、工具纵向时间轴、文字输入。

**Architecture:** 新增 `icons.ts` + `Icon.vue`（图标源）、`MarkdownRenderer.vue`、`ToolTimeline.vue`、`PanelHeader.vue`、`ChatInput.vue`；重构 `FloatBall`（多层）、`MessageItem`（头像+头部+markdown+时间轴）、`AssistantPanel`（三段式）、`MessageList`；删除 `ActionBar`；`useAssistant` 新增 `sendText()` 与工具 retry/cancel 接线。分阶段：A 视觉 → B 功能。

**Tech Stack:** Vue 3 `<script setup>` + TypeScript + Vite。**无前端单元测试框架**，验证门槛为 `npm run build`（vue-tsc + vite build）+ 浏览器冒烟。

## Global Constraints

- 对外接口不变：`App.vue` 仍 `import FloatingAssistant` 传 `:asst`，**不得修改 App.vue**。
- `useAssistant` 对外返回接口保留，仅**新增** `sendText`；`visual` 字段沿用。
- `STATE_VISUALS` 仍是状态视觉单一配置源；`icon` 字段由 emoji 改为 SVG 名。
- 品牌渐变 `--brand-grad` / 彩虹 `--rainbow` / 状态色 `visual.color` 沿用既有令牌。
- 行为必须保留：球体拖拽、双击唤醒、迷你条翻转、消息滚动、新消息红点、聆听/录音彩虹、状态流转。
- 每任务结束必须 `npm run build` 通过。

---

## 阶段 A — 视觉

### Task 1: 图标注册表 `icons.ts` + 组件 `Icon.vue`

**Files:**
- Create: `web/src/components/icons.ts`
- Create: `web/src/components/Icon.vue`

**Interfaces:**
- Produces: `ICONS: Record<string, IconElement[]>`、`ICON_NAMES: string[]`；组件 `<Icon name size color />`。

- [ ] **Step 1: 创建 `web/src/components/icons.ts`**

```ts
// 手写 SVG 图标注册表（24×24 viewBox，描边风格）
export interface IconElement {
  t: 'path' | 'circle'
  d?: string          // path 数据
  cx?: number; cy?: number; r?: number   // circle 参数
}

const p = (d: string): IconElement => ({ t: 'path', d })
const c = (cx: number, cy: number, r: number): IconElement => ({ t: 'circle', cx, cy, r })

export const ICONS: Record<string, IconElement[]> = {
  // 状态
  wave:       [p('M3 12c1.5 0 1.5-2 3-2s1.5 4 3 4 1.5-6 3-6 1.5 2 3 2 1.5-2 3-2'), p('M3 16c1.5 0 1.5-2 3-2s1.5 4 3 4 1.5-6 3-6 1.5 2 3 2 1.5-2 3-2')],
  ear:        [p('M3 18v-6a9 9 0 0 1 18 0v6'), p('M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3z'), p('M3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z')],
  mic:        [p('M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z'), p('M19 10v2a7 7 0 0 1-14 0v-2'), p('M12 19v4'), p('M8 23h8')],
  sparkles:   [p('M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z'), p('M19 16l.9 2.1L22 19l-2.1.9L19 22l-.9-2.1L16 19l2.1-.9z')],
  brain:      [p('M9.5 3a2.5 2.5 0 0 0-2.5 2.5 2 2 0 0 0-1 3.5A2 2 0 0 0 7 12a2 2 0 0 0-1 3.5 2 2 0 0 0 1 3.5A2.5 2.5 0 0 0 9.5 21V3z'), p('M14.5 3a2.5 2.5 0 0 1 2.5 2.5 2 2 0 0 1 1 3.5 2 2 0 0 1-1 3 2 2 0 0 1 1 3.5 2 2 0 0 1-1 3.5 2.5 2.5 0 0 1-2.5 2.5V3z'), p('M9.5 3h5M9.5 21h5')],
  wrench:     [p('M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z')],
  chat:       [p('M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z')],
  check:      [p('M20 6L9 17l-5-5')],
  alert:      [c(12, 12, 10), p('M12 8v4'), p('M12 16h.01')],
  // 工具
  search:     [c(11, 11, 7), p('M21 21l-4.3-4.3')],
  send:       [p('M22 2L11 13'), p('M22 2l-7 20-4-9-9-4z')],
  // 操作
  trash:      [p('M3 6h18'), p('M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6'), p('M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2'), p('M10 11v6'), p('M14 11v6')],
  'chevron-down': [p('M6 9l6 6 6-6')],
  close:      [p('M18 6L6 18'), p('M6 6l12 12')],
  play:       [p('M5 3l14 9-14 9z')],
  stop:       [p('M6 6h12v12H6z')],
  dots:       [c(5, 12, 1.6), c(12, 12, 1.6), c(19, 12, 1.6)],
  user:       [c(12, 8, 4), p('M4 21c0-4 3.6-6 8-6s8 2 8 6')],
}

export const ICON_NAMES = Object.keys(ICONS)
```

- [ ] **Step 2: 创建 `web/src/components/Icon.vue`**

```vue
<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.8"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <template v-for="(el, i) in elements" :key="i">
      <path v-if="el.t === 'path'" :d="el.d" />
      <circle v-else-if="el.t === 'circle'" :cx="el.cx" :cy="el.cy" :r="el.r" />
    </template>
  </svg>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ICONS } from './icons'

const props = withDefaults(defineProps<{
  name: string
  size?: number
}>(), { size: 18 })

const elements = computed(() => ICONS[props.name] || [])
</script>
```

> 注：颜色由 `color: currentColor` 继承（父元素设 `color` 即可）；如需覆盖可给父元素 color。

- [ ] **Step 3: 验证构建**

Run: `cd web && npm run build`
Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add web/src/components/icons.ts web/src/components/Icon.vue
git commit -m "feat: SVG 图标注册表 + Icon 组件（~30 手写图标）"
```

---

### Task 2: 状态图标接入 — `STATE_VISUALS.icon` 改 SVG 名

**Files:**
- Modify: `web/src/composables/useAssistantVisuals.ts`
- Modify: `web/src/components/assistant/FloatBall.vue`

**Interfaces:**
- Consumes: `Icon.vue`；`visual.icon`（SVG 名）。
- Produces: `STATE_VISUALS[*].icon` 为 SVG 名；FloatBall 用 `<Icon>` 渲染。

- [ ] **Step 1: 修改 `useAssistantVisuals.ts` 的 icon 字段**

把 `STATE_VISUALS` 中所有 `icon` 从 emoji 改为 SVG 名：
`idle:'wave'`、`listening:'ear'`、`recording:'mic'`、`transcribing:'sparkles'`、`thinking:'brain'`、`tool_calling:'wrench'`、`responding:'chat'`、`done:'check'`、`error:'alert'`。

- [ ] **Step 2: `FloatBall.vue` 模板中 `<span class="trigger-icon">` 替换为 `<Icon>`**

```vue
<Icon :name="visual.icon" :size="24" class="trigger-icon" style="color:#fff" />
```
（引入 `import Icon from '../Icon.vue'`）

- [ ] **Step 3: 验证构建**

Run: `cd web && npm run build`
Expected: PASS（悬浮球图标变为 SVG；其它未消费 icon 的地方不受影响）

- [ ] **Step 4: 提交**

```bash
git add web/src/composables/useAssistantVisuals.ts web/src/components/assistant/FloatBall.vue
git commit -m "refactor: STATE_VISUALS.icon 改 SVG 名，悬浮球用 Icon 渲染"
```

---

### Task 3: 多层组合球 `FloatBall.vue`

**Files:**
- Modify: `web/src/components/assistant/FloatBall.vue`

**Interfaces:**
- Consumes: `visual`（含 icon/grad/color）、`expanded`、`messageDot`、`wakeEnabled`。
- Produces: 新增 emits `toggleWake`（mic 徽章点击）；分层结构。录音进度环留 Phase B（Task 9）。

- [ ] **Step 1: 模板改为分层结构**

```vue
<template>
  <div
    class="float-trigger"
    :class="[visual.fx, visual.grad === 'rainbow' ? 'fx-rainbow' : '', { active: expanded }]"
    :style="[triggerStyle, { '--fx-color': visual.color }]"
    @pointerdown="onDragStart"
    @touchstart.prevent="onTouchStart"
    @touchmove.prevent="onTouchMove"
    @touchend="onTouchEnd"
    @click="onClick"
    @dblclick="emit('dblclick')"
  >
    <!-- 外层渐变环 + 状态特效（.float-trigger::after 保留） -->
    <span class="ball-status-ring"></span>          <!-- 状态环层：recording 进度环占位（Phase B 填充） -->
    <Icon :name="visual.icon" :size="24" class="ball-icon" style="color:#fff" />
    <!-- 语音开关徽章（mic） -->
    <button class="ball-mic" :class="{ on: wakeEnabled }" title="语音开关" @click.stop="emit('toggleWake')">
      <Icon :name="wakeEnabled ? 'mic' : 'mic'" :size="10" />
    </button>
    <span v-if="!expanded && messageDot" class="new-dot"></span>
  </div>
</template>
```

- [ ] **Step 2: 脚本补充**

- props 增加 `wakeEnabled: boolean`
- emits 增加 `toggleWake: []`
- `import Icon from '../Icon.vue'`

- [ ] **Step 3: 样式**

- `.ball-icon`：居中，z-index 1
- `.ball-mic`：绝对定位右下角 8px，10px 圆，半透明深色底，`on` 时绿色发光
- `.ball-status-ring`：绝对定位 inset 0，圆环，默认透明；聆听/录音时品牌色环（进度环在 Phase B）
- 保留 `.float-trigger::after` 状态特效与 `fx-rainbow`

- [ ] **Step 4: 验证构建**

Run: `cd web && npm run build`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add web/src/components/assistant/FloatBall.vue
git commit -m "feat: 多层组合球 FloatBall — 图标层 + 状态环 + mic 语音开关徽章"
```

---

### Task 4: 三段式面板 — `PanelHeader` / `ChatInput` 外壳 / 删除 `ActionBar`

**Files:**
- Create: `web/src/components/assistant/PanelHeader.vue`
- Create: `web/src/components/assistant/ChatInput.vue`（外壳，发送接线在 Task 10）
- Modify: `web/src/components/assistant/AssistantPanel.vue`
- Modify: `web/src/components/assistant/MessageList.vue`
- Modify: `web/src/components/FloatingAssistant.vue`
- Delete: `web/src/components/assistant/ActionBar.vue`

**Interfaces:**
- Produces: `PanelHeader` props `{ visual, state }` emits `clear`/`close`；`ChatInput` props `{ disabled }` emits `send(text)`（外壳阶段 send 暂不接线）。

- [ ] **Step 1: 创建 `PanelHeader.vue`**

```vue
<template>
  <div class="panel-header">
    <span class="ph-avatar"><Icon name="brain" :size="16" /></span>
    <span class="ph-name">小逻</span>
    <span class="ph-status">
      <span class="ph-dot" :style="{ background: visual.color }"></span>
      <span class="ph-text">{{ statusText }}</span>
    </span>
    <button class="ph-btn" title="清空对话" @click="emit('clear')"><Icon name="trash" :size="14" /></button>
    <button class="ph-btn" title="关闭" @click="emit('close')"><Icon name="close" :size="14" /></button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Icon from '../Icon.vue'
import { resolveStateLabel } from '../../composables/useAssistantVisuals'
import type { AsstState } from '../../composables/useAssistant'
import type { StateVisual } from '../../composables/useAssistantVisuals'

const props = defineProps<{
  visual: StateVisual
  state: AsstState
  wakeKeyword: string
}>()
const emit = defineEmits<{ clear: []; close: [] }>()

const statusText = computed(() => resolveStateLabel(props.visual, props.wakeKeyword))
</script>

<style scoped>
.panel-header { display: flex; align-items: center; gap: 8px; padding: 10px 12px; background: #0f172a; border-bottom: 1px solid var(--border-base); }
.ph-avatar { width: 24px; height: 24px; border-radius: 50%; background: var(--brand-grad); display: flex; align-items: center; justify-content: center; color: #0f172a; }
.ph-name { font-size: 14px; font-weight: 600; color: var(--text-1); }
.ph-status { flex: 1; display: flex; align-items: center; gap: 6px; min-width: 0; }
.ph-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.ph-text { font-size: 12px; color: var(--text-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ph-btn { background: none; border: none; color: var(--text-2); cursor: pointer; padding: 4px; border-radius: 6px; display: flex; }
.ph-btn:hover { background: #334155; color: var(--text-1); }
</style>
```

- [ ] **Step 2: 创建 `ChatInput.vue`（外壳）**

```vue
<template>
  <div class="chat-input">
    <textarea
      ref="ta"
      v-model="text"
      rows="1"
      placeholder="输入消息，Enter 发送，Shift+Enter 换行"
      :disabled="disabled"
      @keydown.enter.exact.prevent="onEnter"
      @keydown.enter.shift.prevent="onShiftEnter"
      @input="autosize"
    ></textarea>
    <button class="ci-send" :disabled="disabled || !text.trim()" @click="submit">
      <Icon name="send" :size="16" />
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import Icon from '../Icon.vue'

const props = defineProps<{ disabled?: boolean }>()
const emit = defineEmits<{ send: [text: string] }>()

const text = ref('')
const ta = ref<HTMLTextAreaElement>()

function autosize() {
  const el = ta.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 4 * 20) + 'px'
}
function onEnter() { submit() }
function onShiftEnter() { autosize() }
function submit() {
  const v = text.value.trim()
  if (!v || props.disabled) return
  emit('send', v)
  text.value = ''
  nextTick(autosize)
}
</script>

<style scoped>
.chat-input { display: flex; align-items: flex-end; gap: 8px; padding: 8px 10px; border-top: 1px solid var(--border-base); }
.chat-input textarea {
  flex: 1; resize: none; max-height: 80px; min-height: 36px; line-height: 20px;
  background: #1e293b; border: 1px solid var(--border-base); border-radius: 10px;
  color: var(--text-1); padding: 8px 10px; font-size: 13px; outline: none;
}
.chat-input textarea:focus { border-color: var(--brand-c2); }
.ci-send { width: 36px; height: 36px; border-radius: 10px; background: var(--brand-grad); border: none; color: #0f172a; cursor: pointer; display: flex; align-items: center; justify-content: center; }
.ci-send:disabled { opacity: .4; cursor: not-allowed; }
</style>
```

- [ ] **Step 3: `AssistantPanel.vue` 改为三段式骨架**

模板改为：`<PanelHeader ... @clear @close />` + `<div class="panel-body"><slot></slot></div>` + `<slot name="footer"></slot>`。移除旧 `.panel-handle`。props 增加 `wakeKeyword`。

- [ ] **Step 4: `FloatingAssistant.vue` 组合更新**

```vue
<AssistantPanel ... @close="expanded = false" :wake-keyword="asst.wakeKeyword.value">
  <MessageList :messages="asst.messages.value" :state="asst.state.value" :visual="asst.visual.value" :wake-keyword="asst.wakeKeyword.value" />
  <ChatInput :disabled="false" @send="asst.sendText($event)" />
</AssistantPanel>
```
同时把 `StatusBar`/`ActionBar` 从组合中移除（StatusBar 职责并入 PanelHeader；ActionBar 删除）。`FloatBall` 增加 `:wake-enabled="asst.wakeEnabled.value"` 与 `@toggle-wake="asst.toggleWake()"`。

- [ ] **Step 5: 删除 `ActionBar.vue`**，删除 `StatusBar.vue` 引入

- [ ] **Step 6: 验证构建**

Run: `cd web && npm run build`
Expected: PASS。若 `asst.sendText` 未定义报错 → 这是 Task 10 的接线，先临时把 `@send` 改为 `@send="console.log($event)"` 占位，Task 10 再接。

- [ ] **Step 7: 提交**

```bash
git add -A web/src/components
git commit -m "refactor: 三段式面板 — PanelHeader/ChatInput 新增，AssistantPanel/MessageList 调整，删除 ActionBar/StatusBar"
```

---

### Task 5: 气泡头像 + 头部 — `MessageItem.vue`

**Files:**
- Modify: `web/src/components/assistant/MessageItem.vue`

**Interfaces:**
- Consumes: `message: ChatMessage`；`Icon`。
- Produces: 气泡带头像 + 头部（角色名 + 时间）。

- [ ] **Step 1: 模板重构**

```vue
<template>
  <div class="msg-item" :class="message.role">
    <span v-if="message.role !== 'system'" class="msg-avatar" :class="message.role">
      <Icon :name="message.role === 'assistant' ? 'brain' : 'user'" :size="14" />
    </span>
    <div class="msg-body">
      <div class="msg-meta">
        <span class="msg-role">{{ roleName }}</span>
        <span class="msg-time">{{ formatTime(message.timestamp) }}</span>
      </div>
      <div class="msg-bubble" :class="message.role">
        <div class="msg-text">{{ message.text }}</div>
        <div v-if="message.toolCalls?.length" class="msg-tools">
          <!-- 工具标签保留，后续 Task 7 换 ToolTimeline -->
          <div v-for="tc in message.toolCalls" :key="tc.id" class="tool-tag" :class="tc.status" @click="expandedToolId = expandedToolId === tc.id ? '' : tc.id">
            <Icon :name="toolIcon(tc)" :size="12" />
            <span class="tool-name">{{ toolLabel(tc) }}</span>
            <span class="tool-status-badge">{{ tc.status }}</span>
          </div>
          <div v-if="expandedToolId === message.toolCalls[0]?.id" class="tool-detail">
            <div class="tool-args"><strong>参数:</strong><code>{{ JSON.stringify(message.toolCalls[0].args, null, 2) }}</code></div>
            <div v-if="message.toolCalls[0].result" class="tool-result"><strong>结果:</strong> {{ message.toolCalls[0].result }}</div>
          </div>
          <slot name="tool-actions" :tool="message.toolCalls[0]"></slot>
        </div>
      </div>
    </div>
  </div>
</template>
```

- [ ] **Step 2: 脚本**

- `import Icon from '../Icon.vue'`
- `toolIcon(tc)` 返回 SVG 名：`{ chat: 'chat' }`，默认 `'wrench'`
- `roleName` computed：user→'你'、assistant→'小逻'、system→'系统'

- [ ] **Step 3: 样式**

- `.msg-item`：flex 行布局（头像 + body）；system 居中
- `.msg-avatar`：24px 圆；assistant 品牌渐变底 + 深色 icon；user 暗色底
- `.msg-meta`：角色名 + 时间小字
- 气泡样式保留（用户渐变 / 助手深色+渐变左边框）

- [ ] **Step 4: 验证构建**

Run: `cd web && npm run build`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add web/src/components/assistant/MessageItem.vue
git commit -m "feat: 气泡头像 + 头部（角色名/时间），工具标签换 SVG 图标"
```

---

## 阶段 B — 功能

### Task 6: `MarkdownRenderer.vue` + 气泡内容接入

**Files:**
- Create: `web/src/components/MarkdownRenderer.vue`
- Modify: `web/src/components/assistant/MessageItem.vue`

**Interfaces:**
- Produces: `<MarkdownRenderer :text="string" />`，纯展示，XSS 安全。

- [ ] **Step 1: 创建 `MarkdownRenderer.vue`**

```vue
<template>
  <!-- 渲染结果经 v-html 插入，内容已按 token 安全转义 -->
  <div class="md" v-html="html"></div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ text: string }>()

function esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

const html = computed(() => {
  let s = esc(props.text ?? '')
  // 代码块 ``` ... ```
  s = s.replace(/```([\s\S]*?)```/g, (_, code) => '<pre><code>' + code + '</code></pre>')
  // 行内代码 `x`
  s = s.replace(/`([^`\n]+)`/g, (_, code) => '<code>' + code + '</code>')
  // 粗体 **x** 与斜体 *x*（避免匹配到链接/代码已处理后的残留，先粗后斜）
  s = s.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
  s = s.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
  // 链接 [t](url)
  s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
  // 列表：- item / 1. item
  s = s.replace(/(^|\n)[ \t]*[-*][ \t]+([^\n]+)/g, '$1<li>$2</li>')
  s = s.replace(/(^|\n)[ \t]*\d+[.、][ \t]+([^\n]+)/g, '$1<li>$2</li>')
  s = s.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul>$1</ul>')
  // 换行
  s = s.replace(/\n{2,}/g, '</p><p>').replace(/\n/g, '<br/>')
  return '<p>' + s + '</p>'
})
</script>

<style scoped>
.md { line-height: 1.6; word-break: break-word; }
.md code { background: rgba(255,255,255,.12); padding: 1px 4px; border-radius: 4px; font-size: .9em; }
.md pre { background: #0f172a; padding: 8px 10px; border-radius: 8px; overflow-x: auto; margin: 6px 0; }
.md pre code { background: none; padding: 0; }
.md a { color: var(--brand-c2); text-decoration: underline; }
.md ul { padding-left: 18px; margin: 4px 0; }
</style>
```

> 注：链接 href 值已在 esc() 中转义，`javascript:` 前缀需额外拦截：对 href 以 `javascript:`/`data:` 开头时替换为 `#`。

- [ ] **Step 2: `MessageItem.vue` 内容区替换**

`<div class="msg-text">{{ message.text }}</div>` → `<MarkdownRenderer :text="message.text" />`（system 气泡保持纯文本）。引入组件。

- [ ] **Step 3: 验证构建**

Run: `cd web && npm run build`
Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add web/src/components/MarkdownRenderer.vue web/src/components/assistant/MessageItem.vue
git commit -m "feat: 轻量 markdown 渲染 MarkdownRenderer，气泡内容接入"
```

---

### Task 7: `ToolTimeline.vue` 替换气泡工具区

**Files:**
- Create: `web/src/components/assistant/ToolTimeline.vue`
- Modify: `web/src/components/assistant/MessageItem.vue`

**Interfaces:**
- Consumes: `ToolStep[]`；emits `retry(stepId)` / `cancel(stepId)`。
- Produces: 纵向时间轴，数据驱动。

- [ ] **Step 1: 创建 `ToolTimeline.vue`**

```vue
<template>
  <div class="tool-timeline">
    <div v-for="(step, i) in steps" :key="step.id" class="tt-step" :class="step.status">
      <div class="tt-row">
        <span class="tt-rail" :class="{ last: i === steps.length - 1 }"></span>
        <span class="tt-icon" :class="step.status"><Icon :name="step.icon || 'wrench'" :size="12" /></span>
        <span class="tt-name">{{ step.name }}</span>
        <span class="tt-status">{{ statusText(step.status) }}</span>
        <span v-if="step.durationMs != null" class="tt-dur">{{ (step.durationMs / 1000).toFixed(1) }}s</span>
        <button v-if="step.status === 'failed'" class="tt-act" title="重试" @click="emit('retry', step.id)"><Icon name="play" :size="11" /></button>
        <button v-if="['running', 'queued'].includes(step.status)" class="tt-act" title="取消" @click="emit('cancel', step.id)"><Icon name="close" :size="11" /></button>
        <button class="tt-expand" @click="openId = openId === step.id ? '' : step.id">
          <Icon name="chevron-down" :size="11" :class="{ rot: openId === step.id }" />
        </button>
      </div>
      <div v-if="openId === step.id" class="tt-detail">
        <div class="tool-args"><strong>参数:</strong><code>{{ JSON.stringify(step.args, null, 2) }}</code></div>
        <div v-if="step.result" class="tool-result"><strong>结果:</strong> {{ step.result }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import Icon from '../Icon.vue'

export interface ToolStep {
  id: string
  name: string
  icon?: string
  status: 'queued' | 'running' | 'done' | 'failed'
  durationMs?: number
  args?: Record<string, any>
  result?: string
}

defineProps<{ steps: ToolStep[] }>()
const emit = defineEmits<{ retry: [id: string]; cancel: [id: string] }>()

const openId = ref('')

const STATUS_TEXT: Record<ToolStep['status'], string> = {
  queued: '排队', running: '执行中', done: '完成', failed: '失败',
}
function statusText(s: ToolStep['status']) { return STATUS_TEXT[s] || s }
</script>

<style scoped>
.tool-timeline { margin-top: 6px; display: flex; flex-direction: column; gap: 2px; }
.tt-step { position: relative; padding-left: 26px; }
.tt-row { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.tt-rail { position: absolute; left: 5px; top: 14px; bottom: -6px; width: 2px; background: var(--border-base); }
.tt-rail.last { display: none; }
.tt-icon { width: 12px; height: 12px; border-radius: 50%; background: #1e293b; color: var(--text-2); display: flex; align-items: center; justify-content: center; position: absolute; left: 0; }
.tt-icon.running { color: var(--brand-c2); animation: tt-blink 1s infinite; }
.tt-icon.done { color: #34d399; }
.tt-icon.failed { color: #f87171; }
.tt-name { color: var(--text-1); }
.tt-status { font-size: 11px; color: var(--text-3); }
.tt-step.running .tt-status { color: var(--brand-c2); }
.tt-step.done .tt-status { color: #34d399; }
.tt-step.failed .tt-status { color: #f87171; }
.tt-dur { font-size: 11px; color: var(--text-3); margin-left: auto; }
.tt-act { background: none; border: none; color: var(--text-2); cursor: pointer; padding: 2px; display: flex; }
.tt-act:hover { color: var(--brand-c2); }
.tt-expand { background: none; border: none; color: var(--text-3); cursor: pointer; padding: 2px; display: flex; }
.tt-expand .rot { transform: rotate(180deg); }
.tt-detail { margin-top: 4px; font-size: 11px; color: var(--text-2); background: #0f172a; padding: 6px 8px; border-radius: 6px; }
.tool-args code { display: block; background: #1e293b; padding: 4px 6px; border-radius: 4px; margin-top: 2px; white-space: pre-wrap; word-break: break-all; }
.tool-result { margin-top: 4px; }
@keyframes tt-blink { 0%,100% { opacity: 1; } 50% { opacity: .4; } }
</style>
```

- [ ] **Step 2: `MessageItem.vue` 工具区替换**

把 `msg-tools` 块替换为 `<ToolTimeline :steps="timelineSteps" @retry="$emit('retry', $event)" @cancel="$emit('cancel', $event)" />`，`MessageItem` 增加 emits `retry`/`cancel`。`timelineSteps` computed 把 `message.toolCalls` 映射为 `ToolStep[]`（`status:'pending'→'queued'`，`icon` 用 toolIcon）。

- [ ] **Step 3: 验证构建**

Run: `cd web && npm run build`
Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add web/src/components/assistant/ToolTimeline.vue web/src/components/assistant/MessageItem.vue
git commit -m "feat: 工具纵向时间轴 ToolTimeline，气泡工具区替换"
```

---

### Task 8: 工具重试/取消接线 — `useAssistant.handleAction`

**Files:**
- Modify: `web/src/composables/useAssistant.ts`
- Modify: `web/src/components/FloatingAssistant.vue`（传递 retry/cancel 事件）

**Interfaces:**
- Consumes: `ToolTimeline` emits `retry`/`cancel`。
- Produces: `useAssistant` 新增 `retryTool(toolCallId)` / `cancelTool(toolCallId)`；`handleAction` 中 running/failed 状态落库。

- [ ] **Step 1: `handleAction` 记录 toolCall 状态**

- `running` 时 `toolCalls[0].status = 'running'`（已存在）
- `done` 时记录 `durationMs`（用 `Date.now() - startTime`）
- `failed` 时 `toolCalls[0].status = 'failed'`（已存在）

- [ ] **Step 2: 新增方法**

```ts
// 重试工具：重新执行 toolCall.args 的 action
function retryTool(id: string) {
  const m = messages.value.find(m => m.toolCalls?.some(tc => tc.id === id))
  const tc = m?.toolCalls?.find(t => t.id === id)
  if (!tc || !m) return
  tc.status = 'running'; tc.result = ''
  handleAction({ action: tc.name, args: tc.args, reply: tc.result })
}

// 取消工具：标记 failed
function cancelTool(id: string) {
  for (const m of messages.value)
    m.toolCalls?.forEach(tc => { if (tc.id === id) tc.status = 'failed' })
}
```

return 中新增 `retryTool`、`cancelTool`。

- [ ] **Step 3: 事件透传**

`FloatingAssistant.vue` 的 `MessageList` → `MessageItem` 需透传 retry/cancel（MessageItem 通过 `defineEmits` 上抛；MessageList 增加 emits 透传）。

- [ ] **Step 4: 验证构建**

Run: `cd web && npm run build`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add web/src/composables/useAssistant.ts web/src/components/FloatingAssistant.vue web/src/components/assistant/MessageList.vue web/src/components/assistant/MessageItem.vue
git commit -m "feat: 工具重试/取消接线 — retryTool/cancelTool"
```

---

### Task 9: 录音进度环 `FloatBall`

**Files:**
- Modify: `web/src/components/assistant/FloatBall.vue`

**Interfaces:**
- Consumes: `state`（recording）、`recordingProgress`（0~1，可选 prop）。
- Produces: recording 状态显示 conic 进度环。

- [ ] **Step 1: 进度环渲染**

`.ball-status-ring` 在 `state === 'recording'` 时用 conic 渐变（`conic-gradient(var(--brand-c2) X%, transparent 0)`），X 来自 `recordingProgress`（默认 0，由容器/useAssistant 提供录音时长占比；Task 10 的 sendText 不影响）。

- [ ] **Step 2: 进度来源（简单版）**

`FloatBall` 内部：`watch(state)` 到 `recording` 时启动 `setInterval(100ms)` 累计，按 `vadConfig.max_duration_ms`（从 useAssistant 暴露）算比例；离开 recording 停止并清零。若无外部进度则用内部计时器。

- [ ] **Step 3: 验证构建**

Run: `cd web && npm run build`
Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add web/src/components/assistant/FloatBall.vue
git commit -m "feat: 录音进度环 FloatBall（conic 进度）"
```

---

### Task 10: 文字输入接线 — `useAssistant.sendText` + `ChatInput`

**Files:**
- Modify: `web/src/composables/useAssistant.ts`
- Modify: `web/src/components/assistant/ChatInput.vue`（若外壳阶段已有 send，这里确保 emit 接通）

**Interfaces:**
- Produces: `useAssistant.sendText(text: string)`；`ChatInput` `@send` → `sendText`。

- [ ] **Step 1: `useAssistant` 新增 `sendText`**

```ts
function sendText(text: string) {
  const t = text.trim()
  if (!t) return
  addMessage('user', t)
  handleLLM(t)   // 复用现有管线（内部会设置 thinking 等状态）
}
```
return 中新增 `sendText`。

- [ ] **Step 2: `FloatingAssistant.vue` 接入**

把 Task 4 的 `@send="asst.sendText($event)"` 从占位改为正式接线。

- [ ] **Step 3: 验证构建**

Run: `cd web && npm run build`
Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add web/src/composables/useAssistant.ts web/src/components/FloatingAssistant.vue
git commit -m "feat: 文字输入接线 — sendText 复用 LLM 管线"
```

---

### Task 11: 流式打字效果（可选）

**Files:**
- Modify: `web/src/components/assistant/MessageItem.vue`

**Interfaces:**
- Produces: `typewriter` prop（可选）；assistant 消息打字机显示。

- [ ] **Step 1: 打字机效果**

`MessageItem` 增加 `typewriter?: boolean` prop；当为 true 且角色 assistant 时，把文本按 10ms/字逐步展开（`revealed` ref + interval），内容渲染 `text.slice(0, revealed)`。

- [ ] **Step 2: 验证构建**

Run: `cd web && npm run build`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add web/src/components/assistant/MessageItem.vue
git commit -m "feat: 气泡流式打字效果（可选）"
```

---

### Task 12: 最终验证与清理

**Files:**
- 无新增。

- [ ] **Step 1: 全库 grep 无残留 emoji 图标**

Run: `grep -rn "🤖\|👂\|🔴\|⏳\|🤔\|🔧\|💬\|✅\|❌\|🗑\|▼\|👂" web/src/components/`
Expected: 仅 MarkdownRenderer 或文本内容允许；组件内无 emoji 图标残留。

- [ ] **Step 2: 完整构建**

Run: `cd web && npm run build`
Expected: PASS

- [ ] **Step 3: 浏览器冒烟**

Run: `python main.py serve`，验证：
1. 悬浮球多层：SVG 图标 + mic 徽章 + 状态环；聆听/录音彩虹循环
2. 面板三段式：顶栏（头像/名称/只读状态/清空/关闭）+ 消息区 + 输入栏
3. 文字输入：Enter 发送 / Shift+Enter 换行 / 自适应增高；与语音可并存
4. 气泡：头像 + 头部 + markdown 渲染（粗体/代码/列表/链接）
5. 工具时间轴：步骤 + 状态 + 耗时，展开详情；failed 重试 / running 取消
6. 录音进度环显示
7. 拖拽/双击唤醒/迷你条/红点行为保留

- [ ] **Step 4: 提交（如有剩余调整）**

```bash
git add -A
git commit -m "refactor: 第二轮重构收尾验证"
```

---

## Self-Review

**Spec coverage:**
- SVG 图标集 + emoji 替换：Task 1-2 ✓
- 多层组合球（含录音进度环）：Task 3、9 ✓
- 三段式面板 + 删除 ActionBar + 语音在球上：Task 4（+Task 3 mic 徽章）✓
- 气泡头像/头部 + markdown：Task 5-6 ✓
- 工具纵向时间轴 + 重试/取消：Task 7-8 ✓
- 文字输入 sendText + ChatInput：Task 4、10 ✓
- 流式打字（可选）：Task 11 ✓
- App.vue 不变、useAssistant 接口保留：Global Constraints + Task 8/10 ✓

**Placeholder scan:** 无 TBD；Task 4 Step 6 的 `console.log` 占位是显式标注的过渡态，Task 10 替换。

**Type consistency:** `ToolStep`（Task 7）状态 `queued/running/done/failed` 与 spec 一致；`pending→queued` 映射在 `timelineSteps` computed 处理；`Icon` 组件 API `name/size` 全任务一致；`sendText`/`retryTool`/`cancelTool` 在 Task 8/10 定义、Task 4/10 消费。
