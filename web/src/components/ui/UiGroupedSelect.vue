<template>
  <!-- 分组下拉：触发器 + Teleport 面板；每组一个标题，选项跨组扁平化以支持键盘导航。
       Grouped select: trigger + teleported panel; one header per group, options flattened
       across groups so keyboard navigation stays linear. -->
  <div class="ui-gselect-wrap" ref="wrapRef">
    <button
      ref="triggerRef"
      class="ui-gselect"
      type="button"
      role="combobox"
      :aria-expanded="open"
      :disabled="disabled"
      @click="toggle"
      @keydown="onKeydown"
    >
      <span class="ui-gselect-value" :class="{ ph: !selectedLabel }">
        {{ selectedLabel || placeholder }}
      </span>
      <UiFieldChevron :open="open" />
    </button>

    <Teleport to="body">
      <div
        v-if="open"
        :id="listId"
        class="ui-gselect-panel"
        :class="{ up: flipUp }"
        :style="menuStyle"
        role="listbox"
      >
        <input
          v-if="searchable"
          v-model="query"
          class="ui-gselect-search"
          type="text"
          placeholder="搜索…"
          @keydown="onKeydown"
        />
        <div v-if="!flatFiltered.length" class="ui-gselect-empty">无匹配项</div>
        <div v-for="g in filteredGroups" :key="g.label" class="ui-gselect-group">
          <div class="ui-gselect-group-label">{{ g.label }}</div>
          <button
            v-for="opt in g.options"
            :key="opt.value"
            type="button"
            class="ui-gselect-option"
            :class="{ sel: opt.value === modelValue, on: opt.value === activeValue }"
            :disabled="opt.disabled"
            role="option"
            :aria-selected="opt.value === modelValue"
            @mousemove="setActive(opt.value)"
            @click="pick(opt)"
          >
            <span class="ui-gselect-option-label">{{ opt.label }}</span>
            <UiIcon v-if="opt.value === modelValue" name="check" :size="13" class="ui-gselect-check" />
          </button>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
/**
 * 分组下拉（v-model + groups）。用于模型选择：组标题是供应商，选项是模型。
 * 复用 `useAnchoredPanel` 的定位/翻转/外点关闭/键盘循环；搜索框按 label/value 过滤，
 * 整组无匹配时连组标题一起隐藏。
 *
 * Grouped select (v-model + groups), used by the model picker (provider headers, model
 * options). Reuses `useAnchoredPanel` for positioning/flip/outside-close/keyboard wrap;
 * the search box filters by label/value and hides groups with no match.
 */
import { computed, nextTick, ref, watch } from 'vue'
import UiFieldChevron from './UiFieldChevron.vue'
import UiIcon from './UiIcon.vue'
import { useAnchoredPanel } from './useAnchoredPanel'
import type { GroupedOption, OptionGroup } from './groupedTypes'

const props = withDefaults(defineProps<{
  groups: OptionGroup[]
  modelValue: string
  placeholder?: string
  disabled?: boolean
  searchable?: boolean
}>(), { placeholder: '请选择', disabled: false, searchable: true })

const emit = defineEmits<{ 'update:modelValue': [v: string] }>()

const wrapRef = ref<HTMLElement>()
const triggerRef = ref<HTMLButtonElement>()
const query = ref('')

/** 全部选项（跨组扁平）。All options, flattened across groups. */
const flat = computed(() => props.groups.flatMap(g => g.options))
/** 选中项显示文本。Display label of the selected option. */
const selectedLabel = computed(
  () => flat.value.find(o => o.value === props.modelValue)?.label || '',
)

/** 搜索过滤后的分组（空组隐藏）。Filtered groups (empty groups dropped). */
const filteredGroups = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return props.groups
  return props.groups
    .map(g => ({
      ...g,
      options: g.options.filter(
        o => o.label.toLowerCase().includes(q) || o.value.toLowerCase().includes(q),
      ),
    }))
    .filter(g => g.options.length > 0)
})
/** 过滤后的扁平选项（键盘导航用）。Flattened filtered options for keyboard nav. */
const flatFiltered = computed(() => filteredGroups.value.flatMap(g => g.options))

/** 某 value 在过滤列表中的索引（找不到回落到 0）。Index of a value in the filtered list. */
function indexOfValue(value: string): number {
  return Math.max(0, flatFiltered.value.findIndex(o => o.value === value))
}

const { open, flipUp, menuStyle, activeIndex, listId, place, show, close, move } = useAnchoredPanel({
  anchor: () => triggerRef.value,
  wrap: () => wrapRef.value,
  count: () => flatFiltered.value.length,
  idPrefix: 'ui-gselect',
})

/** 当前键盘活动项的 value。Value of the keyboard-active option. */
const activeValue = computed(() => flatFiltered.value[activeIndex.value]?.value ?? '')

/** 开合面板；打开时清空搜索并聚焦搜索框。Toggle the panel; reset search and focus it. */
function toggle(): void {
  if (props.disabled) return
  if (open.value) {
    close()
    return
  }
  query.value = ''
  show(indexOfValue(props.modelValue))
  void nextTick(() => {
    const input = document.querySelector(`#${listId} .ui-gselect-search`) as HTMLInputElement | null
    input?.focus()
  })
}

/** 选中一项。Pick one option. */
function pick(option: GroupedOption): void {
  if (option.disabled) return
  emit('update:modelValue', option.value)
  close()
}

/** 键盘活动项跟随鼠标。Keyboard-active item follows the pointer. */
function setActive(value: string): void {
  activeIndex.value = indexOfValue(value)
}

/** 键盘：Esc 关闭、↑↓ 移动、Enter 选中。Keyboard handling. */
function onKeydown(e: KeyboardEvent): void {
  if (e.key === 'Escape') {
    close()
    e.stopPropagation()
    return
  }
  if (!open.value) {
    if (e.key === 'Enter' || e.key === 'ArrowDown') {
      e.preventDefault()
      toggle()
    }
    return
  }
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    move(1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    move(-1)
  } else if (e.key === 'Enter') {
    e.preventDefault()
    const option = flatFiltered.value[activeIndex.value]
    if (option) pick(option)
  }
}

watch(filteredGroups, () => {
  activeIndex.value = 0
  void nextTick(place)
})
</script>

<style scoped>
.ui-gselect-wrap { position: relative; display: inline-flex; min-width: 0; }
.ui-gselect {
  display: inline-flex; align-items: center; gap: var(--sp-2); min-width: 0;
  padding: var(--sp-q6) var(--sp-2); border-radius: var(--r-md);
  border: 1px solid var(--border-soft); background: rgba(15, 23, 42, .55);
  color: var(--text-1); font-size: var(--fs-2xs); cursor: pointer; max-width: 220px;
}
.ui-gselect:hover:not(:disabled) { border-color: var(--brand-c2); color: var(--brand-c2); }
.ui-gselect:disabled { opacity: .55; cursor: not-allowed; }
.ui-gselect-value { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ui-gselect-value.ph { color: var(--text-3); }

.ui-gselect-panel {
  position: fixed; z-index: 9990; max-height: 260px; overflow-y: auto;
  padding: var(--sp-1); border-radius: var(--r-md);
  border: 1px solid var(--glass-border); background: var(--surface-raised);
  box-shadow: var(--shadow-2); backdrop-filter: blur(14px);
}
.ui-gselect-search {
  width: 100%; box-sizing: border-box; margin-bottom: var(--sp-1);
  padding: var(--sp-q6) var(--sp-2); border-radius: var(--r-sm);
  border: 1px solid var(--border-soft); background: rgba(15, 23, 42, .7);
  color: var(--text-1); font-size: var(--fs-2xs); outline: none;
}
.ui-gselect-search:focus { border-color: var(--brand-c2); }
.ui-gselect-group + .ui-gselect-group { margin-top: var(--sp-1); }
.ui-gselect-group-label {
  padding: var(--sp-1) var(--sp-2) 2px; font-size: var(--fs-2xs);
  color: var(--text-3); letter-spacing: .04em; text-transform: uppercase;
}
.ui-gselect-option {
  display: flex; align-items: center; justify-content: space-between; gap: var(--sp-2);
  width: 100%; padding: var(--sp-q6) var(--sp-2); border: none; border-radius: var(--r-sm);
  background: none; color: var(--text-2); font-size: var(--fs-2xs); text-align: left; cursor: pointer;
}
.ui-gselect-option.on { background: rgba(103, 232, 249, .08); color: var(--text-1); }
.ui-gselect-option.sel { color: var(--brand-c2); }
.ui-gselect-option:disabled { opacity: .5; cursor: not-allowed; }
.ui-gselect-option-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ui-gselect-check { color: var(--brand-c2); flex-shrink: 0; }
.ui-gselect-empty { padding: var(--sp-2); color: var(--text-3); font-size: var(--fs-2xs); }
</style>
