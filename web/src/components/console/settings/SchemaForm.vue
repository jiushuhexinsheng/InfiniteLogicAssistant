<template>
  <!-- Schema 驱动参数表单：后端给字段定义，前端只按 type 渲染控件。
       Schema-driven parameter form: the backend defines fields, the frontend only renders
       by type. -->
  <div class="schema-form">
    <template v-for="group in groups" :key="group.key">
      <h4 v-if="group.fields.length" class="sf-group">{{ group.label }}</h4>
      <div class="sf-grid">
        <BiFormItem
          v-for="f in group.fields"
          :key="f.key"
          :label-zh="f.label?.zh || f.key"
          :label-en="f.label?.en || ''"
          :hint-zh="f.hint?.zh || ''"
          :hint-en="f.hint?.en || ''"
        >
          <input
            v-if="f.type === 'slider'"
            class="sf-range"
            type="range"
            :min="f.min ?? 0"
            :max="f.max ?? 1"
            :step="f.step ?? 0.01"
            :value="Number(values[f.key] ?? f.default ?? 0)"
            @input="set(f.key, Number(($event.target as HTMLInputElement).value))"
          />
          <UiInput
            v-else-if="f.type === 'number'"
            type="number"
            :min="f.min"
            :max="f.max"
            :step="f.step"
            :model-value="values[f.key] ?? f.default"
            @update:model-value="v => set(f.key, v === '' ? '' : Number(v))"
          />
          <UiSelect
            v-else-if="f.type === 'select'"
            :model-value="String(values[f.key] ?? f.default ?? '')"
            :options="selectOptions(f)"
            @update:model-value="v => setSelect(f, v)"
          />
          <UiToggle
            v-else-if="f.type === 'switch'"
            :model-value="!!(values[f.key] ?? f.default)"
            @update:model-value="v => set(f.key, v)"
          />
          <UiTextarea
            v-else-if="f.type === 'textarea'"
            :model-value="String(values[f.key] ?? f.default ?? '')"
            @update:model-value="v => set(f.key, v)"
          />
          <UiInput
            v-else
            :model-value="String(values[f.key] ?? f.default ?? '')"
            @update:model-value="v => set(f.key, v)"
          />
        </BiFormItem>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * SchemaForm：按后端参数 schema 渲染设置控件，并直接写回传入的配置对象。
 *
 * SchemaForm renders settings controls from the backend schema and writes back into the
 * provided config object. Parent owns persistence (Save button).
 */
import { computed } from 'vue'
import BiFormItem from './BiFormItem.vue'
import { UiInput, UiSelect, UiTextarea, UiToggle } from '../../ui'

export interface SchemaField {
  key: string
  target?: string | null
  type: 'slider' | 'number' | 'select' | 'switch' | 'text' | 'textarea'
  group?: 'common' | 'model'
  label?: { zh: string; en: string }
  hint?: { zh: string; en: string }
  default?: unknown
  min?: number
  max?: number
  step?: number
  options?: { value: string | number; label: string }[]
}

const props = withDefaults(defineProps<{
  params: SchemaField[]
  values: Record<string, any>
}>(), { params: () => [] })

const emit = defineEmits<{ change: [] }>()

const groups = computed(() => [
  { key: 'model', label: '模型参数 / Model', fields: props.params.filter(f => (f.group || 'model') === 'model') },
  { key: 'common', label: '通用参数 / Common', fields: props.params.filter(f => f.group === 'common') },
])

function set(key: string, value: unknown) {
  props.values[key] = value
  emit('change')
}

/** UiSelect 只接受字符串 value；显示时转字符串，写回时还原原始类型（如 window_size 数字）。
 *  UiSelect only accepts string values; stringify for display and restore the raw type on write. */
function selectOptions(f: SchemaField) {
  return (f.options || []).map(o => ({ value: String(o.value), label: o.label }))
}

function setSelect(f: SchemaField, v: string | number) {
  const raw = (f.options || []).find(o => String(o.value) === String(v))?.value ?? v
  set(f.key, raw)
}
</script>

<style scoped>
.schema-form { display: flex; flex-direction: column; gap: var(--sp-3); }
.sf-group {
  margin: var(--sp-2) 0 0;
  font-size: var(--fs-2xs); font-weight: 600; color: var(--text-3);
  letter-spacing: .04em; text-transform: uppercase;
}
.sf-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--sp-2); }
.sf-range { width: 100%; accent-color: var(--brand-c2); }
</style>
