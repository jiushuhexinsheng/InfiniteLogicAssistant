<template>
  <!-- 可输入组合框：UiInput 外壳 + 与 UiSelect 同风格的自绘建议面板。
       2026-10-11 起替换原生 <datalist>（其弹层是浏览器系统样式，无法定制，与项目
       暗色玻璃风割裂）。自由输入完全不受限 —— 建议层只是提示与快选。

       Typeable combobox: a UiInput shell plus a self-drawn suggestion panel styled
       like UiSelect. Replaces the native <datalist> (its popup is OS-styled and
       clashes with the project's dark-glass look). Free typing stays unrestricted —
       the suggestion layer is only a hint/quick-pick. -->
  <div class="ui-combo" ref="wrapRef">
    <input
      ref="inputRef"
      class="ui-input"
      :value="modelValue"
      :placeholder="placeholder"
      :disabled="disabled"
      @input="onInput"
      @focus="openPanel"
      @keydown="onKeydown"
      v-bind="$attrs"
    />
    <!-- 装饰性 chevron 底座（对齐 UiSelect 触发器，标明「有建议层」；面板开合旋转）。
         Decorative chevron seat (matches the UiSelect trigger, signals "suggestions
         available"; rotates with the panel). -->
    <span class="ui-combo-chevron" :class="{ open }"><UiIcon name="chevron-down" :size="14" /></span>
    <Teleport to="body">
      <ul
        v-if="open && filtered.length"
        ref="menuRef"
        class="ui-select-menu"
        :class="{ up: flipUp }"
        :style="menuStyle"
      >
        <li
          v-for="(opt, i) in filtered"
          :id="`${listId}-${i}`"
          :key="opt"
          class="ui-select-option"
          :class="{ on: i === activeIndex, sel: opt === modelValue }"
          @mousemove="activeIndex = i"
          @mousedown.prevent="pick(opt)"
        >
          <span class="ui-select-option-label">{{ opt }}</span>
          <UiIcon v-if="opt === modelValue" name="check" :size="13" class="ui-select-check" />
        </li>
      </ul>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
/**
 * 可输入组合框（v-model + options 数组）。API 与 UiInput 一致，另收建议列表。
 * Typeable combobox (v-model + options array). Same API as UiInput plus a suggestion list.
 *
 * 与 UiSelect 的分工：UiSelect = 纯选择（值必须来自选项）；UiCombobox = 可手输 +
 * 建议（模型名/音色/工具名这类「通常选、偶尔造」的字段）。面板定位/键盘/关闭策略
 * 与 UiSelect 同构（Teleport body、空间不足上翻、↑↓/Enter/Esc、300ms 焦点滚动宽限）。
 *
 * Division of labour: UiSelect = pure pick (value must come from options); UiCombobox =
 * free typing + suggestions (fields like model/voice/tool names that are usually picked
 * but sometimes invented). Panel positioning, keyboard and close policies mirror
 * UiSelect (teleport to body, flip up when short, ↑↓/Enter/Esc, 300ms focus-scroll
 * grace).
 */
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import UiIcon from './UiIcon.vue'

/** 组件 Props：绑定值/建议列表/占位/禁用。Component props: value, suggestion list, placeholder, disabled. */
const props = withDefaults(defineProps<{
  modelValue?: string
  options?: string[]
  placeholder?: string
  disabled?: boolean
}>(), { modelValue: '', options: () => [], placeholder: '', disabled: false })

/** 事件：值变更（输入即发、点选也发）。Emits value change (live typing and picks). */
const emit = defineEmits<{ 'update:modelValue': [v: string] }>()

/** 面板唯一 id。Unique panel id. */
const listId = `ui-combo-${Math.random().toString(36).slice(2, 8)}`

const inputRef = ref<HTMLInputElement>()
const menuRef = ref<HTMLUListElement>()
const wrapRef = ref<HTMLDivElement>()

const open = ref(false)
/** 打开时刻（毫秒）：焦点滚动宽限期基准。Open timestamp (focus-scroll grace anchor). */
let openedAt = 0
const activeIndex = ref(0)
const flipUp = ref(false)
const menuStyle = ref<Record<string, string>>({})
/** 是否正在键入（聚焦打开时展示全部建议；键入后才按输入过滤 —— 否则当前值
 *  会把其它建议滤掉，如值 'Chloe' 打开就看不到 'Mia'）。
 *  Whether the user is typing (focus opens with all suggestions; filtering only starts
 *  while typing — otherwise the current value filters everything else out, e.g. value
 *  'Chloe' hides 'Mia'). */
const typed = ref(false)

/** 过滤建议：未键入 = 全部；键入中 = 大小写不敏感包含匹配。
 *  Filter suggestions: not typing → all; typing → case-insensitive contains. */
const filtered = computed<string[]>(() => {
  const list = props.options.filter(Boolean)
  if (!typed.value) return list
  const q = (props.modelValue || '').toLowerCase()
  if (!q) return list
  return list.filter(o => o.toLowerCase().includes(q))
})

/** 打开面板（无建议时不打开，纯自由输入）。Open the panel (no suggestions → stays closed). */
function openPanel() {
  typed.value = false
  if (!filtered.value.length) return
  open.value = true
  openedAt = performance.now()
  const sel = filtered.value.indexOf(props.modelValue)
  activeIndex.value = sel >= 0 ? sel : 0
  positionMenu()
}

function close() {
  open.value = false
}

function onInput(e: Event) {
  typed.value = true
  emit('update:modelValue', (e.target as HTMLInputElement).value)
  activeIndex.value = 0
  // 输入改变过滤集后若面板开着，重新定位（结果条数变了，高度可能变化）。
  // Reposition while open (the result count — and height — may change).
  nextTick(() => {
    if (open.value) {
      if (!filtered.value.length) close()
      else positionMenu()
    }
  })
}

/** 定位面板（锚定输入框；下方不足上翻）。Position the panel (anchor to input; flip up). */
function positionMenu() {
  const el = inputRef.value
  if (!el) return
  const r = el.getBoundingClientRect()
  const PANEL_MAX = 260
  const spaceBelow = window.innerHeight - r.bottom
  const spaceAbove = r.top
  flipUp.value = spaceBelow < Math.min(PANEL_MAX + 8, spaceAbove) && spaceAbove > spaceBelow
  menuStyle.value = {
    left: `${Math.round(r.left)}px`,
    width: `${Math.round(r.width)}px`,
    ...(flipUp.value
      ? { bottom: `${Math.round(window.innerHeight - r.top + 4)}px` }
      : { top: `${Math.round(r.bottom + 4)}px` }),
  }
}

/** 选中建议（mousedown 触发，先于 input 失焦）。Pick a suggestion (mousedown fires before blur). */
function pick(opt: string) {
  emit('update:modelValue', opt)
  close()
  inputRef.value?.focus()
}

/** 键盘活动项滚动可见。Scroll the keyboard-active item into view. */
function scrollActive() {
  nextTick(() => {
    document.getElementById(`${listId}-${activeIndex.value}`)?.scrollIntoView?.({ block: 'nearest' })
  })
}

function move(d: number) {
  const n = filtered.value.length
  if (!n) return
  activeIndex.value = (activeIndex.value + d + n) % n
  scrollActive()
}

/** 键盘：↑↓ 导航、Enter 选中（面板关闭时 Enter 不吞，保留给表单提交）、Esc/Tab 关闭。
 *  Keyboard: ↑↓ navigate, Enter picks (Enter with the panel closed is NOT swallowed —
 *  left for form submission), Esc/Tab close. */
function onKeydown(e: KeyboardEvent) {
  switch (e.key) {
    case 'ArrowDown':
      if (!open.value && filtered.value.length) { e.preventDefault(); openPanel() }
      else if (open.value) { e.preventDefault(); move(1) }
      break
    case 'ArrowUp':
      if (open.value) { e.preventDefault(); move(-1) }
      break
    case 'Enter':
      if (open.value) { e.preventDefault(); pick(filtered.value[activeIndex.value]) }
      break
    case 'Escape':
      if (open.value) { e.preventDefault(); close() }
      break
    case 'Tab':
      close()
      break
  }
}

/** 外部指针按下关闭（面板在 body 下）。Close on outside pointerdown (panel lives under body). */
function onDocPointer(e: PointerEvent) {
  const t = e.target as Node
  if (wrapRef.value?.contains(t)) return
  if (menuRef.value?.contains(t)) return
  close()
}

/**
 * 滚动关闭（与 UiSelect 同策略）：放行面板自身滚动与打开后 300ms 内的焦点/连锁滚动
 * （浏览器为把输入框滚进视口的异步微滚，不排除会「一输入就关」）。
 * Close on scroll (same policy as UiSelect): panel's own scroll and focus/chain scrolls
 * within 300ms of opening are exempt (the browser's async micro-scroll to bring the
 * input into view — without the exemption the panel closes on the first keystroke).
 */
function onScroll(e: Event) {
  const t = e.target
  if (menuRef.value && t instanceof Node && menuRef.value.contains(t)) return
  if (performance.now() - openedAt < 300) return
  if (open.value) close()
}

function onResize() {
  if (open.value) close()
}

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onDocPointer)
  window.removeEventListener('scroll', onScroll, true)
  window.removeEventListener('resize', onResize)
})

// 打开时挂全局监听，关闭时摘除（随开随挂）。Attach global listeners while open, detach when closed.
watch(open, (v) => {
  if (v) {
    document.addEventListener('pointerdown', onDocPointer)
    window.addEventListener('scroll', onScroll, true)
    window.addEventListener('resize', onResize)
  } else {
    document.removeEventListener('pointerdown', onDocPointer)
    window.removeEventListener('scroll', onScroll, true)
    window.removeEventListener('resize', onResize)
  }
})
</script>

<style scoped>
.ui-combo { position: relative; width: 100%; }
/* 触发器右侧留出 chevron 底座位（与 UiSelect 触发器同款排版）。
   Reserve room for the chevron seat on the right (same trigger layout as UiSelect). */
.ui-combo .ui-input { padding-right: 38px; }

/* chevron 底座：镜像 UiSelect 的 .ui-select-chevron（圆底座、开合旋转）。
   Chevron seat: mirrors UiSelect's .ui-select-chevron (round seat, rotates on toggle). */
.ui-combo-chevron {
  position: absolute; right: 6px; top: 50%;
  transform: translateY(-50%);
  width: 26px; height: 26px; border-radius: 50%;
  display: grid; place-items: center;
  background: var(--surface-control);
  color: var(--text-3);
  pointer-events: none;
  transition: transform var(--dur-base) var(--ease-out), color var(--dur-fast), background var(--dur-fast);
}
.ui-combo-chevron.open {
  transform: translateY(-50%) rotate(180deg);
  color: var(--brand-c2);
  background: rgba(103, 232, 249, .12);
}

/* 弹层样式镜像 UiSelect（scoped 无法共享其样式）——改一处请同步另一处。
   Panel styles mirror UiSelect (scoped styles cannot be shared) — keep the two in sync. */
.ui-select-menu {
  position: fixed;
  z-index: 1000;
  margin: 0; padding: 4px;
  list-style: none;
  max-height: 260px;
  overflow-y: auto;
  background: rgba(10, 15, 28, .96);
  backdrop-filter: blur(14px) saturate(140%);
  -webkit-backdrop-filter: blur(14px) saturate(140%);
  border: 1px solid var(--glass-border);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-3);
  animation: ui-combo-in .12s var(--ease-out);
}
@keyframes ui-combo-in {
  from { opacity: 0; transform: translateY(-4px) scale(.98); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
@media (prefers-reduced-motion: reduce) { .ui-select-menu { animation: none; } }

.ui-select-option {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  padding: 8px 10px;
  border-radius: var(--r-md);
  font-size: var(--fs-xs); color: var(--text-1);
  cursor: pointer;
  transition: background var(--dur-fast), color var(--dur-fast);
}
.ui-select-option-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ui-select-option:hover,
.ui-select-option.on { background: rgba(103, 232, 249, .14); color: var(--brand-c2); }
.ui-select-option.sel { background: rgba(103, 232, 249, .08); color: var(--brand-c2); }
.ui-select-option.sel:hover,
.ui-select-option.sel.on { background: rgba(103, 232, 249, .16); }
.ui-select-check { flex-shrink: 0; color: var(--brand-c2); }
</style>
