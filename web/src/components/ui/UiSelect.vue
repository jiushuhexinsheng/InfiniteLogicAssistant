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

    <!-- 弹层挂 body：不受祖先 overflow 裁剪，空间不足时向上翻转。样式与定位由
         UiPopoverPanel + useAnchoredPanel 提供 —— 与 UiCombobox 共用同一份。
         Panel teleported to body: immune to ancestor overflow, flips up when space runs out.
         Styling and positioning come from UiPopoverPanel + useAnchoredPanel, shared with
         UiCombobox. -->
    <UiPopoverPanel
      v-if="open"
      :list-id="listId"
      :items="options"
      :selected="modelValue"
      :active-index="activeIndex"
      :flip-up="flipUp"
      :panel-style="menuStyle"
      listbox
      @pick="pick"
      @hover="setActive"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * 自绘下拉框组件：`options` 提供选项，v-model 绑定选中值。
 * Custom select: `options` supplies the items, v-model binds the selection.
 *
 * 原先选项是从 slot 里的 `<option>` vnode 解析出来的（在 JS 里递归拆 Fragment 再抽文本），
 * 与 `UiSegmented` / `UiRadioCard` 的 `options` prop 家族风格冲突 —— 已统一到 `options`。
 * 原生 select 的弹层是系统样式无法定制，故用 Teleport 到 body 的自绘面板：暗色玻璃、
 * hover 高亮、选中打勾、空间不足向上翻转；键盘 ↑↓/Home/End/Enter/Esc 走 combobox 模式
 * （焦点留在触发器，aria-activedescendant 指向活动项）。
 *
 * 弹层的定位/翻转/外点关闭/滚动宽限与弹层样式由 `useAnchoredPanel` + `UiPopoverPanel`
 * 提供，与 `UiCombobox` 共用（此前两个文件各有一份逐行重复的实现）。
 *
 * Items used to be parsed out of `<option>` vnodes in the slot (recursively unwrapping
 * Fragments and extracting text in JS), which clashed with the `options`-prop family in
 * `UiSegmented` / `UiRadioCard` — now unified on `options`. The native popup is OS-styled and
 * cannot be customized, hence the teleported custom panel: dark glass, hover highlight, check
 * on selected, flips up when space runs short; keyboard ↑↓/Home/End/Enter/Esc follow the
 * combobox pattern (focus stays on the trigger, aria-activedescendant points at the active item).
 *
 * The panel's positioning / flip / outside-click-close / scroll grace and its styling come from
 * `useAnchoredPanel` + `UiPopoverPanel`, shared with `UiCombobox` — each file used to carry a
 * line-by-line duplicate of both.
 */
import { computed, ref } from 'vue'
import type { SegOption } from './UiSegmented.vue'
import UiIcon from './UiIcon.vue'
import UiPopoverPanel from './UiPopoverPanel.vue'
import { useAnchoredPanel } from './useAnchoredPanel'

/** 组件 Props：选项列表/当前值/禁用/占位文案。Component props: options, current value, disabled, placeholder.
 *  `options` 复用 `SegOption` —— { value, label } 是本目录所有单选族组件共用的选项形状。
 *  `options` reuses `SegOption` — { value, label } is the option shape every single-choice
 *  primitive in this folder shares. */
const props = withDefaults(defineProps<{
  options: SegOption[]
  modelValue?: string
  disabled?: boolean
  placeholder?: string
}>(), { modelValue: '', disabled: false, placeholder: '' })

/** 事件：选中值变更。Event: selection changed. */
const emit = defineEmits<{ 'update:modelValue': [v: string] }>()

/** 触发器 / 外层元素引用。Trigger / wrapper refs. */
const triggerRef = ref<HTMLButtonElement>()
const wrapRef = ref<HTMLDivElement>()

/** 弹层的共享行为（定位/翻转/外点/滚动宽限/键盘循环/随开随挂监听）。
 *  The panel's shared behaviour (positioning / flip / outside-click / scroll grace /
 *  wrap-around keyboard / attach-while-open listeners). */
const panel = useAnchoredPanel({
  anchor: () => triggerRef.value,
  wrap: () => wrapRef.value,
  count: () => props.options.length,
  idPrefix: 'ui-sel',
})
const { open, flipUp, menuStyle, activeIndex, listId } = panel

/**
 * 触发器显示文本：命中选项显示其 label，否则回退原值。
 * Trigger text: the matched option's label, else the raw value.
 */
const displayText = computed(() => {
  const hit = props.options.find(i => i.value === props.modelValue)
  return hit ? hit.label : props.modelValue
})

/** 面板打开。Open the panel. */
function openMenu() {
  if (!props.options.length) {
    // `options` 传空时静默 return 会让「点击无反应」极难排查。
    // A silent return on empty `options` makes "click does nothing" impossible to debug.
    console.warn('[UiSelect] options 为空，面板不打开')
    return
  }
  const sel = props.options.findIndex(i => i.value === props.modelValue)
  // 打开即把选中项滚进可视区（与 UiCombobox 的差异之一）。
  // Scroll the selected item into view on open (one of the deliberate differences from UiCombobox).
  panel.show(sel >= 0 ? sel : 0, true)
}

/** 关闭面板。Close the panel. */
function close() {
  panel.close()
}

/** 切换面板。Toggle the panel. */
function toggle() {
  open.value ? close() : openMenu()
}

/**
 * 选中第 i 项。Pick option i.
 *
 * @param i 选项索引。Option index.
 */
function pick(i: number) {
  const it = props.options[i]
  if (!it) return
  emit('update:modelValue', it.value)
  close()
  triggerRef.value?.focus()
}

/**
 * 同步鼠标悬停项为键盘活动项（弹层的 `hover` 事件）。
 * Mirror a hovered row into the keyboard-active index (the panel's `hover` event).
 *
 * @param i 选项索引。Option index.
 */
function setActive(i: number) {
  activeIndex.value = i
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
      open.value ? panel.move(1) : openMenu()
      break
    case 'ArrowUp':
      e.preventDefault()
      open.value ? panel.move(-1) : (openMenu(), (activeIndex.value = props.options.length - 1))
      break
    case 'Home':
      if (open.value) { e.preventDefault(); activeIndex.value = 0 }
      break
    case 'End':
      if (open.value) { e.preventDefault(); activeIndex.value = props.options.length - 1 }
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
</script>

<style scoped>
.ui-select-wrap { position: relative; display: inline-block; width: 100%; }

/* 触发器外壳：凹陷层次 + 加大圆角 + focus 品牌光晕常驻。
   Trigger shell: inset depth + larger radius + persistent brand focus glow. */
.ui-select {
  width: 100%;
  display: flex; align-items: center; justify-content: space-between; gap: var(--sp-2);
  background: var(--surface-input);
  border: 1px solid var(--border-base);
  border-radius: var(--r-lg);
  color: var(--text-1);
  padding: var(--sp-q10) var(--sp-q38) var(--sp-q10) var(--sp-3);
  font-size: var(--fs-sm); font-family: inherit;
  text-align: left; cursor: pointer;
  min-height: var(--min-target-size);
  box-shadow: var(--shadow-inset);
  transition: border-color var(--dur-fast), box-shadow var(--dur-fast);
}
/* hover 需避开 focus（同 UiInput：防止半透明边框盖掉 focus 实色边框）。
   hover yields to focus (same as UiInput: translucent border must not cover focus's solid border). */
.ui-select:hover:not(:disabled):not(:focus) { border-color: var(--border-hover); }
.ui-select:focus {
  outline: none;
  border-color: var(--brand-c2);
  box-shadow: var(--shadow-inset), var(--focus-glow);
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
</style>
