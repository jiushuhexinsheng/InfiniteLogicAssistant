<template>
  <!-- 锚定弹层外壳：UiSelect 与 UiCombobox 共用。
       这两个组件此前各有一份**逐条镜像**的 scoped 弹层样式（原注释直言「改一处请同步另一处」）
       —— scoped 样式无法跨组件共享，故把「弹层长什么样」收进这个组件，样式只写一遍。

       Anchored panel shell shared by UiSelect and UiCombobox. The two used to carry
       line-by-line mirrored scoped panel styles (the old comment literally said "keep the
       two in sync") — scoped styles cannot be shared, so "what the panel looks like" moves
       into this component and is written once. -->
  <Teleport to="body">
    <ul
      :id="listId"
      class="ui-select-menu"
      :class="{ up: flipUp }"
      :style="panelStyle"
      :role="listbox ? 'listbox' : undefined"
    >
      <li v-if="!items.length" class="ui-select-empty">无选项</li>
      <li
        v-for="(it, i) in items"
        :id="`${listId}-${i}`"
        :key="it.value"
        class="ui-select-option"
        :data-value="listbox ? it.value : undefined"
        :role="listbox ? 'option' : undefined"
        :class="{ on: i === activeIndex, sel: it.value === selected }"
        :aria-selected="listbox ? it.value === selected : undefined"
        @mousemove="emit('hover', i)"
        @click="pickOn === 'click' && emit('pick', i)"
        @mousedown="onRowDown($event, i)"
      >
        <span class="ui-select-option-label">{{ it.label }}</span>
        <UiIcon v-if="it.value === selected" name="check" :size="13" class="ui-select-check" />
      </li>
    </ul>
  </Teleport>
</template>

<!-- 锚定弹层：Teleport 到 body（不受祖先 overflow 裁剪），空间不足时由调用方上翻。
     行选中时机与 listbox 语义按调用方传入 —— 两个消费者在这两点上刻意不同。
     Anchored panel: teleported to body (immune to ancestor overflow), flipped up by the caller
     when space runs short. Pick timing and listbox semantics come from the caller — the two
     consumers differ on those on purpose. -->
<script setup lang="ts">
import UiIcon from './UiIcon.vue'

/** 弹层选项行。One panel row. */
export interface PanelItem {
  /** 选项值（兼作 v-for 的 key 与选中比对）。Option value (doubles as the v-for key and the selection check). */
  value: string
  /** 选项显示文本。Option label. */
  label: string
}

/** 弹层 Props。Panel props. */
const props = withDefaults(defineProps<{
  /** 选项行。The option rows. */
  items: PanelItem[]
  /** 面板唯一 id，同时派生每行的 id（`${listId}-${i}`，供 aria-activedescendant 与 scrollIntoView 使用）。
   *  Panel id; row ids derive from it (for aria-activedescendant and scrollIntoView). */
  listId: string
  /** 当前选中值（打勾 + `.sel` 高亮）。Current value (check mark + `.sel` highlight). */
  selected?: string
  /** 键盘活动项索引（`.on` 高亮）。Keyboard-active index (`.on` highlight). */
  activeIndex?: number
  /** 空间不足向上翻转（`.up`）。Flipped upward (`.up`). */
  flipUp?: boolean
  /** 定位样式，由 useAnchoredPanel 产出。Position styles, produced by useAnchoredPanel. */
  panelStyle?: Record<string, string>
  /** listbox 语义开关（`role=option` / `aria-selected` / `data-value`）：UiSelect 开、UiCombobox 关
   *  —— 后者是可自由输入的建议层，不是必须择一的列表框。
   *  listbox semantics (role=option / aria-selected / data-value): on for UiSelect, off for
   *  UiCombobox, whose panel is a free-typing suggestion layer rather than a pick-one listbox. */
  listbox?: boolean
  /** 选中时机：`click`（UiSelect）或 `mousedown`（UiCombobox —— 抢在输入框失焦前落地，否则先关后选）。
   *  When a row commits: `click` (UiSelect) or `mousedown` (UiCombobox — must land before the
   *  input blurs, or the panel closes first). */
  pickOn?: 'click' | 'mousedown'
}>(), { selected: '', activeIndex: 0, flipUp: false, panelStyle: () => ({}), listbox: false, pickOn: 'click' })

/** 事件：`pick` 提交第 i 行；`hover` 报告鼠标移到第 i 行（由调用方决定是否同步活动项）。
 *  Events: `pick` commits row i; `hover` reports the mouse moving onto row i. */
const emit = defineEmits<{ pick: [index: number]; hover: [index: number] }>()

/**
 * 行内 mousedown：仅 `pickOn === 'mousedown'` 时生效（阻止默认行为 + 提交）。
 * 其余情况**不拦** —— UiSelect 的行使 mousedown 走默认路径，与抽取前一致。
 *
 * Row mousedown: only active when `pickOn === 'mousedown'` (prevent default + commit).
 * Otherwise it stays out of the way, matching the pre-extraction UiSelect row exactly.
 *
 * @param e 鼠标事件。Mouse event.
 * @param i 行索引。Row index.
 */
function onRowDown(e: MouseEvent, i: number) {
  if (props.pickOn !== 'mousedown') return
  e.preventDefault()
  emit('pick', i)
}
</script>

<style scoped>
/* ── 弹层：暗色玻璃 + hover 品牌高亮 + 选中打勾 ──
   Panel: dark glass + brand hover highlight + check on selected. */
.ui-select-menu {
  position: fixed;
  z-index: 1000;
  margin: 0; padding: var(--sp-1);
  list-style: none;
  max-height: 260px;
  overflow-y: auto;
  background: rgba(10, 15, 28, .96);
  backdrop-filter: blur(14px) saturate(140%);
  -webkit-backdrop-filter: blur(14px) saturate(140%);
  border: 1px solid var(--glass-border);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-3);
  animation: ui-panel-in .12s var(--ease-out);
}
@keyframes ui-panel-in {
  from { opacity: 0; transform: translateY(-4px) scale(.98); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
@media (prefers-reduced-motion: reduce) { .ui-select-menu { animation: none; } }

.ui-select-option {
  display: flex; align-items: center; justify-content: space-between; gap: var(--sp-2);
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
