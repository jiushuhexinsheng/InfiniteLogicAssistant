<template>
  <!-- 自绘下拉框：外壳触发器 + Teleport 弹层（原生 select 的系统弹层无法定制样式）。
       Custom select: trigger shell + teleported panel (the native popup cannot be styled). -->
  <div class="ui-select-wrap" ref="wrapRef">
    <button
      ref="triggerRef"
      class="ui-select"
      :data-value="modelValue"
      type="button"
      role="combobox"
      :aria-expanded="open"
      aria-haspopup="listbox"
      :aria-controls="listId"
      :aria-activedescendant="open ? `${listId}-${activeIndex}` : undefined"
      :disabled="disabled"
      @click="toggle"
      @keydown="onKeydown"
      v-bind="$attrs"
    >
      <span class="ui-select-value" :class="{ ph: !displayText }">{{ displayText || placeholder || '请选择' }}</span>
      <span class="ui-select-chevron" :class="{ open }"><UiIcon name="chevron-down" :size="14" /></span>
    </button>

    <!-- 弹层挂 body：不受祖先 overflow 裁剪，空间不足时向上翻转。
         Panel teleported to body: immune to ancestor overflow, flips up when space runs out. -->
    <Teleport to="body">
      <ul
        v-if="open"
        :id="listId"
        ref="menuRef"
        class="ui-select-menu"
        :class="{ up: flipUp }"
        role="listbox"
        :style="menuStyle"
      >
        <li v-if="!items.length" class="ui-select-empty">无选项</li>
        <li
          v-for="(it, i) in items"
          :id="`${listId}-${i}`"
          :key="it.value"
          class="ui-select-option"
          role="option"
          :data-value="it.value"
          :class="{ on: i === activeIndex, sel: it.value === modelValue }"
          :aria-selected="it.value === modelValue"
          @mousemove="activeIndex = i"
          @click="pick(i)"
        >
          <span class="ui-select-option-label">{{ it.label }}</span>
          <UiIcon v-if="it.value === modelValue" name="check" :size="13" class="ui-select-check" />
        </li>
      </ul>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
/**
 * 自绘下拉框组件（API 与原生版一致：v-model + slot 内 `<option>` 提供选项）。
 * Custom select (same API as the native version: v-model + `<option>` items in the slot).
 *
 * 选项数据从 slot 的 option vnode 解析——调用方零改动。原生 select 的弹层是
 * 系统样式无法定制，故用 Teleport 到 body 的自绘面板：暗色玻璃、hover 高亮、
 * 选中打勾、空间不足向上翻转；键盘 ↑↓/Home/End/Enter/Esc 走 combobox 模式
 * （焦点留在触发器，aria-activedescendant 指向活动项）。
 *
 * Option data is parsed from the slot's option vnodes — zero call-site changes.
 * The native popup is OS-styled and cannot be customized, hence the teleported
 * custom panel: dark glass, hover highlight, check on selected, flips up when
 * space runs short; keyboard ↑↓/Home/End/Enter/Esc follow the combobox pattern
 * (focus stays on the trigger, aria-activedescendant points at the active item).
 */
import { ref, computed, useSlots, nextTick, onBeforeUnmount, watch } from 'vue'
import type { VNode } from 'vue'
import UiIcon from './UiIcon.vue'

/** 组件 Props：当前值/禁用/占位文案。Component props: current value, disabled, placeholder. */
const props = withDefaults(defineProps<{
  modelValue?: string
  disabled?: boolean
  placeholder?: string
}>(), { modelValue: '', disabled: false, placeholder: '' })

/** 事件：选中值变更。Event: selection changed. */
const emit = defineEmits<{ 'update:modelValue': [v: string] }>()

const slots = useSlots()

/** 面板唯一 id（setup 内一次性生成）。Unique panel id (generated once in setup). */
const listId = `ui-sel-${Math.random().toString(36).slice(2, 8)}`

/** 触发器 / 面板 / 外层元素引用。Trigger / panel / wrapper refs. */
const triggerRef = ref<HTMLButtonElement>()
const menuRef = ref<HTMLUListElement>()
const wrapRef = ref<HTMLDivElement>()

/** 面板开合。Panel open state. */
const open = ref(false)
/** 打开时刻（毫秒）：焦点滚动/连锁滚动的宽限期基准。Open timestamp (ms): grace-period anchor for focus/chain scrolls. */
let openedAt = 0
/** 键盘活动项索引。Keyboard-active option index. */
const activeIndex = ref(0)
/** 空间不足时向上翻转。Flip upward when space runs short. */
const flipUp = ref(false)
/** 面板定位样式（fixed，锚定触发器）。Panel position (fixed, anchored to the trigger). */
const menuStyle = ref<Record<string, string>>({})

/** 单条选项。One option. */
interface SelItem {
  value: string
  label: string
}

/**
 * 递归提取 vnode 子树中的纯文本。Recursively extract plain text from a vnode subtree.
 *
 * @param c children（string | vnode 数组 | null）。Children (string | vnode array | null).
 * @returns 拼接后的文本。Concatenated text.
 */
function vnodeText(c: unknown): string {
  if (typeof c === 'string') return c
  if (Array.isArray(c)) return c.map(vnodeText).join('')
  if (c && typeof c === 'object' && 'children' in (c as any)) return vnodeText((c as any).children)
  return ''
}

/**
 * 递归收集 slot 中的 `<option>`。Recursively collect `<option>` nodes from the slot.
 *
 * Vue 3 会把 v-for 的列表包进 Fragment（Symbol(v-fgt)），必须展开后才能取到 option。
 * Vue 3 wraps v-for lists in a Fragment (Symbol(v-fgt)); unwrap before reaching the options.
 *
 * @param nodes 当前层 vnode。Current-level vnodes.
 * @param out 收集结果（出参）。Accumulator (output param).
 */
function collectOptions(nodes: VNode[], out: SelItem[]) {
  for (const n of nodes) {
    if (!n) continue
    if (n.type === 'option') {
      const label = vnodeText(n.children)
      const raw = (n.props as Record<string, unknown> | null)?.value
      out.push({ value: raw === undefined || raw === null ? label : String(raw), label })
    } else if (Array.isArray(n.children)) {
      // Fragment / 多子元素：递归展开。Fragment / multi-child: recurse.
      collectOptions(n.children as VNode[], out)
    }
  }
}

/**
 * 从 slot 解析 `<option>` 列表。Parse `<option>` items out of the slot.
 *
 * @returns 选项列表。Option list.
 */
const items = computed<SelItem[]>(() => {
  const out: SelItem[] = []
  collectOptions((slots.default?.() ?? []) as VNode[], out)
  return out
})

/**
 * 触发器显示文本：命中选项显示其 label，否则回退原值。
 * Trigger text: the matched option's label, else the raw value.
 */
const displayText = computed(() => {
  const hit = items.value.find(i => i.value === props.modelValue)
  return hit ? hit.label : props.modelValue
})

/** 面板打开。Open the panel. */
function openMenu() {
  if (!items.value.length) {
    // 选项解析为空 = slot 里的 <option> 没被收集到，静默 return 会让「点击无反应」极难排查。
    // Empty parse = <option>s not collected from the slot; a silent return makes "click does nothing" impossible to debug.
    console.warn('[UiSelect] 选项为空，面板不打开（检查 slot 中的 <option>）')
    return
  }
  open.value = true
  openedAt = performance.now()
  const sel = items.value.findIndex(i => i.value === props.modelValue)
  activeIndex.value = sel >= 0 ? sel : 0
  positionMenu()
  nextTick(() => {
    document.getElementById(`${listId}-${activeIndex.value}`)?.scrollIntoView?.({ block: 'nearest' })
  })
}

/** 关闭面板。Close the panel. */
function close() {
  open.value = false
}

/** 切换面板。Toggle the panel. */
function toggle() {
  open.value ? close() : openMenu()
}

/**
 * 定位面板（锚定触发器；下方空间不足则上翻）。Position the panel (anchor to trigger; flip up when short below).
 */
function positionMenu() {
  const el = triggerRef.value
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

/**
 * 选中第 i 项。Pick option i.
 *
 * @param i 选项索引。Option index.
 */
function pick(i: number) {
  const it = items.value[i]
  if (!it) return
  emit('update:modelValue', it.value)
  close()
  triggerRef.value?.focus()
}

/**
 * 移动键盘活动项（带循环）。Move the keyboard-active item (wraps around).
 *
 * @param d 步进方向（±1）。Step direction (±1).
 */
function move(d: number) {
  const n = items.value.length
  if (!n) return
  activeIndex.value = (activeIndex.value + d + n) % n
  nextTick(() => {
    document.getElementById(`${listId}-${activeIndex.value}`)?.scrollIntoView?.({ block: 'nearest' })
  })
}

/**
 * 键盘处理：↑↓/Home/End 导航，Enter/Space 选择，Esc 关闭。
 * Keyboard: ↑↓/Home/End navigate, Enter/Space select, Esc closes.
 *
 * @param e 键盘事件。Keyboard event.
 */
function onKeydown(e: KeyboardEvent) {
  switch (e.key) {
    case 'ArrowDown':
      e.preventDefault()
      open.value ? move(1) : openMenu()
      break
    case 'ArrowUp':
      e.preventDefault()
      open.value ? move(-1) : (openMenu(), (activeIndex.value = items.value.length - 1))
      break
    case 'Home':
      if (open.value) { e.preventDefault(); activeIndex.value = 0 }
      break
    case 'End':
      if (open.value) { e.preventDefault(); activeIndex.value = items.value.length - 1 }
      break
    case 'Enter':
    case ' ':
      e.preventDefault()
      open.value ? pick(activeIndex.value) : openMenu()
      break
    case 'Escape':
      if (open.value) { e.preventDefault(); close() }
      break
    case 'Tab':
      close()
      break
  }
}

/**
 * 外部指针按下关闭（面板在 body 下，需单独判断）。Close on outside pointerdown (panel lives under body).
 *
 * @param e 指针事件。Pointer event.
 */
function onDocPointer(e: PointerEvent) {
  const t = e.target as Node
  if (wrapRef.value?.contains(t)) return
  if (menuRef.value?.contains(t)) return
  close()
}

/**
 * 滚动关闭面板，但要排除两类「非用户意图」的滚动：
 *
 * 1. 面板自身滚动（max-height 260px 可滚；打开时 scrollIntoView 定位选中项会触发）；
 * 2. **打开瞬间的焦点/连锁滚动** —— 浏览器为了让被点按钮进入视口而微滚祖先容器
 *    （.console-settings 这类 overflow 容器），该滚动是异步分帧的，发生在监听挂载之后，
 *    不排除的话「点开即关」，且只在视口较满的页面（控制台）复现，极难排查。
 *
 * Closes on scroll but excludes two non-user-intent cases: (1) the panel's own
 * scrolling (scrollIntoView on open); (2) the *focus scroll* the browser performs
 * right after opening (asynchronously, after listeners attach) to bring the clicked
 * button into view inside overflow containers like .console-settings — without the
 * grace period the panel closes the instant it opens, only on fuller pages.
 *
 * @param e 滚动事件。Scroll event.
 */
function onScroll(e: Event) {
  const t = e.target
  // 面板内部滚动：放行。Scroll inside the panel: pass.
  if (menuRef.value && t instanceof Node && menuRef.value.contains(t)) return
  // 打开宽限期内的焦点/连锁滚动：放行。Focus/chain scrolls within the grace period: pass.
  if (performance.now() - openedAt < 300) return
  if (open.value) close()
}

/** 窗口缩放：面板锚点失效，直接关闭。Resize invalidates the anchor: close immediately. */
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
.ui-select-wrap { position: relative; display: inline-block; width: 100%; }

/* 触发器外壳：凹陷层次 + 加大圆角 + focus 品牌光晕常驻。
   Trigger shell: inset depth + larger radius + persistent brand focus glow. */
.ui-select {
  width: 100%;
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  background: var(--surface-input);
  border: 1px solid var(--border-base);
  border-radius: var(--r-lg);
  color: var(--text-1);
  padding: 10px 38px 10px 12px;
  font-size: var(--fs-sm); font-family: inherit;
  text-align: left; cursor: pointer;
  min-height: var(--min-target-size);
  box-shadow: inset 0 1px 3px rgba(0, 0, 0, .35);
  transition: border-color var(--dur-fast), box-shadow var(--dur-fast);
}
/* hover 需避开 focus（同 UiInput：防止半透明边框盖掉 focus 实色边框）。
   hover yields to focus (same as UiInput: translucent border must not cover focus's solid border). */
.ui-select:hover:not(:disabled):not(:focus) { border-color: rgba(103, 232, 249, .45); }
.ui-select:focus {
  outline: none;
  border-color: var(--brand-c2);
  box-shadow: inset 0 1px 3px rgba(0, 0, 0, .35), var(--focus-glow);
}
.ui-select:disabled { opacity: .5; cursor: not-allowed; }
.ui-select-value { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ui-select-value.ph { color: var(--text-3); }

/* 自绘 chevron（圆底座）。Custom chevron (round base). */
.ui-select-chevron {
  position: absolute; right: 6px; top: 50%;
  transform: translateY(-50%);
  width: 26px; height: 26px; border-radius: 50%;
  display: grid; place-items: center;
  background: var(--surface-control);
  color: var(--text-3);
  pointer-events: none;
  transition: transform var(--dur-base) var(--ease-out), color var(--dur-fast), background var(--dur-fast);
}
.ui-select-chevron.open {
  transform: translateY(-50%) rotate(180deg);
  color: var(--brand-c2);
  background: rgba(103, 232, 249, .12);
}

/* ── 自绘弹层：暗色玻璃 + hover 品牌高亮 + 选中打勾 ──
   Custom panel: dark glass + brand hover highlight + check on selected. */
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
  animation: ui-sel-in .12s var(--ease-out);
}
@keyframes ui-sel-in {
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
.ui-select-empty {
  padding: 10px; text-align: center;
  font-size: var(--fs-2xs); color: var(--text-3);
}
</style>
