<!-- 设置字段组件：标签 + 控件插槽，支持行内（row）和弹性宽度（grow）布局。Settings field component: label + control slot, supports inline (row) and flexible width (grow) layout. -->
<template>
  <component :is="row ? 'div' : 'label'" class="sf" :class="{ row, grow }">
    <!-- 字段标签。Field label. -->
    <span class="sf-label">{{ label }}</span>
    <!-- 字段控件插槽。Field control slot. -->
    <span class="sf-control"><slot /></span>
  </component>
</template>

<script setup lang="ts">
/** 组件 props：label（标签文本）、row（行内布局）、grow（弹性宽度）。Component props: label (label text), row (inline layout), grow (flexible width). */
withDefaults(defineProps<{ label: string; row?: boolean; grow?: boolean }>(), { row: false, grow: false })
</script>

<style scoped>
.sf { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
.sf.row { flex-direction: row; align-items: center; justify-content: space-between; gap: 12px; }
.sf.grow { flex: 1; }
.sf-label { font-size: var(--fs-2xs); color: var(--text-3); flex-shrink: 0; }
.sf-control { min-width: 0; display: block; }
</style>
