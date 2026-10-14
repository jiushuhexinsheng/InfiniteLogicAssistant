<template>
  <!-- 可输入组合框：UiInput 外壳 + 与 UiSelect 同风格的自绘建议面板。
       2026-10-11 起替换原生 <datalist>（其弹层是浏览器系统样式，无法定制，与项目
       暗色玻璃风割裂）。自由输入完全不受限 —— 建议层只是提示与快选。

       Typeable combobox: a UiInput shell plus a self-drawn suggestion panel styled
       like UiSelect. Replaces the native <datalist> (its popup is OS-styled and
       clashes with the project's dark-glass look). Free typing stays unrestricted —
       the suggestion layer is only a hint/quick-pick. -->
  <div class="ui-combo" ref="wrapRef">
    <!-- 组合 UiInput 而非自绘 <input>：`.ui-input` 的样式挂在 UiInput 组件的 scoped
         属性上，自绘 input 只带本组件 scope —— 类名相同也匹配不到样式（2026-10-11 现场
         白底窄框的根因）。focus/keydown 经 $attrs 落到内层 input。
         Compose UiInput instead of drawing a bare <input>: the `.ui-input` styles live on
         UiInput's scoped attribute, while a locally drawn input only carries this
         component's scope — same class, no styles (the root cause of the white narrow
         box seen in the field on 2026-10-11). focus/keydown fall through $attrs to the
         inner input. -->
    <UiInput
      ref="inputRef"
      :model-value="modelValue"
      :placeholder="placeholder"
      :disabled="disabled"
      autocomplete="off"
      @update:model-value="onValue"
      @focus="openPanel"
      @keydown="onKeydown"
      v-bind="$attrs"
    />
    <!-- 装饰性 chevron 底座（对齐 UiSelect 触发器，标明「有建议层」；面板开合旋转）。
         Decorative chevron seat (matches the UiSelect trigger, signals "suggestions
         available"; rotates with the panel). -->
    <UiFieldChevron :open="open" />
    <!-- 弹层：样式与定位由 UiPopoverPanel + useAnchoredPanel 提供（与 UiSelect 共用）。
         差异在于**没有 listbox 语义**（这是建议层，不是必须择一的列表框）、选中时机走
         mousedown（抢在输入框失焦前落地，否则先关后选）、且不因选空而渲染空态行。
         Panel: styling and positioning come from UiPopoverPanel + useAnchoredPanel (shared
         with UiSelect). The differences are deliberate — no listbox semantics (this is a
         suggestion layer, not a pick-one listbox), pick on mousedown (must land before the
         input blurs), and no empty-state row (an empty suggestion set never opens the panel). -->
    <UiPopoverPanel
      v-if="open && filtered.length"
      :list-id="listId"
      :items="comboItems"
      :selected="modelValue"
      :active-index="activeIndex"
      :flip-up="flipUp"
      :panel-style="menuStyle"
      pick-on="mousedown"
      @pick="i => pick(filtered[i])"
      @hover="setActive"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * 可输入组合框（v-model + options 数组）。API 与 UiInput 一致，另收建议列表。
 * Typeable combobox (v-model + options array). Same API as UiInput plus a suggestion list.
 *
 * 与 UiSelect 的分工：UiSelect = 纯选择（值必须来自选项）；UiCombobox = 可手输 +
 * 建议（模型名/音色/工具名这类「通常选、偶尔造」的字段）。面板的定位/键盘/关闭/样式
 * 与 UiSelect 同构，由 `useAnchoredPanel` + `UiPopoverPanel` 提供（此前两个文件各有一份
 * 逐行重复的实现）；两者刻意不同的地方写在模板注释里。
 *
 * Division of labour: UiSelect = pure pick (value must come from options); UiCombobox =
 * free typing + suggestions (fields like model/voice/tool names that are usually picked
 * but sometimes invented). Panel positioning, keyboard, close policy and styling mirror
 * UiSelect and now come from `useAnchoredPanel` + `UiPopoverPanel` (each file used to carry a
 * line-by-line duplicate); the deliberate differences are documented in the template.
 */
import { computed, nextTick, ref } from 'vue'
import type { ComponentPublicInstance } from 'vue'
import UiFieldChevron from './UiFieldChevron.vue'
import UiInput from './UiInput.vue'
import UiPopoverPanel from './UiPopoverPanel.vue'
import { useAnchoredPanel } from './useAnchoredPanel'

/** 组件 Props：绑定值/建议列表/占位/禁用。Component props: value, suggestion list, placeholder, disabled. */
const props = withDefaults(defineProps<{
  modelValue?: string
  options?: string[]
  placeholder?: string
  disabled?: boolean
}>(), { modelValue: '', options: () => [], placeholder: '', disabled: false })

/** 事件：值变更（输入即发、点选也发）。Emits value change (live typing and picks). */
const emit = defineEmits<{ 'update:modelValue': [v: string] }>()

const inputRef = ref<ComponentPublicInstance>()
const wrapRef = ref<HTMLDivElement>()

/**
 * 取内层真实 input 元素。UiInput 是 v-if/v-else 条件根（片段），$el 可能是注释锚点
 * 或 number 分支的外层 div —— 逐层解析到真正的 <input>。
 * The underlying input element. UiInput has conditional roots (a fragment), so $el may
 * be a comment anchor or the number branch's wrapper div — resolve down to the real
 * <input>.
 *
 * @returns 内层 input 元素。The inner input element.
 */
function inputEl(): HTMLInputElement | undefined {
  const root = inputRef.value?.$el as Node | undefined
  if (!root) return undefined
  if (root instanceof HTMLInputElement) return root
  if (root instanceof Element) return root.querySelector('input') ?? undefined
  return root.parentElement?.querySelector('input') ?? undefined   // 注释锚点 → 宿主容器
}

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

/** 弹层选项：字符串建议映射成 { value, label }（弹层行的形状）。
 *  Panel rows: the string suggestions mapped to { value, label }. */
const comboItems = computed(() => filtered.value.map(v => ({ value: v, label: v })))

/** 弹层的共享行为（定位/翻转/外点/滚动宽限/键盘循环/随开随挂监听）。
 *  The panel's shared behaviour (positioning / flip / outside-click / scroll grace /
 *  wrap-around keyboard / attach-while-open listeners). */
const panel = useAnchoredPanel({
  anchor: () => inputEl(),
  wrap: () => wrapRef.value,
  count: () => filtered.value.length,
  idPrefix: 'ui-combo',
})
const { open, flipUp, menuStyle, activeIndex, listId } = panel

/** 打开面板（无建议时不打开，纯自由输入）。Open the panel (no suggestions → stays closed). */
function openPanel() {
  typed.value = false
  if (!filtered.value.length) return
  const sel = filtered.value.indexOf(props.modelValue)
  panel.show(sel >= 0 ? sel : 0)
}

/** 关闭面板。Close the panel. */
function close() {
  panel.close()
}

/**
 * 输入回调：写值 + 重算过滤集；面板开着就重新定位或关闭。
 * Input callback: write the value, recompute the filter, and either reposition or close.
 *
 * @param v 输入值。Typed value.
 */
function onValue(v: string) {
  typed.value = true
  emit('update:modelValue', v)
  activeIndex.value = 0
  // 输入改变过滤集后若面板开着，重新定位（结果条数变了，高度可能变化）。
  // Reposition while open (the result count — and height — may change).
  nextTick(() => {
    if (open.value) {
      if (!filtered.value.length) close()
      else panel.place()
    }
  })
}

/**
 * 选中建议（mousedown 触发，先于 input 失焦）。Pick a suggestion (mousedown fires before blur).
 *
 * @param opt 选中的建议文本。The picked suggestion.
 */
function pick(opt: string) {
  emit('update:modelValue', opt)
  close()
  inputEl()?.focus()
}

/**
 * 同步鼠标悬停项为键盘活动项（弹层的 `hover` 事件）。
 * Mirror a hovered row into the keyboard-active index (the panel's `hover` event).
 *
 * @param i 建议索引。Suggestion index.
 */
function setActive(i: number) {
  activeIndex.value = i
}

/**
 * 键盘：↑↓ 导航、Enter 选中（面板关闭时 Enter 不吞，保留给表单提交）、Esc/Tab 关闭。
 * Keyboard: ↑↓ navigate, Enter picks (Enter with the panel closed is NOT swallowed —
 * left for form submission), Esc/Tab close.
 *
 * @param e 键盘事件。Keyboard event.
 */
function onKeydown(e: KeyboardEvent) {
  switch (e.key) {
    case 'ArrowDown':
      if (!open.value && filtered.value.length) { e.preventDefault(); openPanel() }
      else if (open.value) { e.preventDefault(); panel.move(1) }
      break
    case 'ArrowUp':
      if (open.value) { e.preventDefault(); panel.move(-1) }
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
</script>

<style scoped>
.ui-combo { position: relative; width: 100%; }
/* 触发器右侧留出 chevron 底座位（与 UiSelect 触发器同款排版）。
   Reserve room for the chevron seat on the right (same trigger layout as UiSelect). */
.ui-combo .ui-input { padding-right: var(--sp-q38); }

</style>
