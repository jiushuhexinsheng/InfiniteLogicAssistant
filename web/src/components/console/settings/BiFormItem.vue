<template>
  <!-- 双语表单行：中文主标签 + 英文副标签 + 控件 + 中英帮助文本。
       Bilingual form row: zh/en label, control slot, zh/en hint. -->
  <component :is="row ? 'div' : 'label'" class="bfi" :class="{ row, grow }">
    <BiLabel :zh="labelZh" :en="labelEn" class="bfi-label" />
    <span class="bfi-control"><slot /></span>
    <span v-if="hintZh || hintEn" class="bfi-hint">
      <span v-if="hintZh">{{ hintZh }}</span>
      <span v-if="hintEn" class="bfi-hint-en">{{ hintEn }}</span>
    </span>
  </component>
</template>

<script setup lang="ts">
/**
 * 双语表单行（设置页统一入口）。所有设置控件都应通过它或 SettingsField 渲染，
 * 避免每个页面各写一套 label/hint。
 *
 * Shared bilingual form row for every settings control.
 */
import BiLabel from './BiLabel.vue'

withDefaults(defineProps<{
  labelZh: string
  labelEn?: string
  hintZh?: string
  hintEn?: string
  row?: boolean
  grow?: boolean
}>(), {
  labelEn: '',
  hintZh: '',
  hintEn: '',
  row: false,
  grow: false,
})
</script>

<style scoped>
.bfi { display: flex; flex-direction: column; gap: var(--sp-q6); min-width: 0; }
.bfi.row { flex-direction: row; align-items: center; justify-content: space-between; gap: var(--sp-3); }
.bfi.grow { flex: 1; }
.bfi-label { font-size: var(--fs-2xs); color: var(--text-3); flex-shrink: 0; }
.bfi-control { min-width: 0; display: block; }
.bfi-hint {
  display: flex; flex-direction: column; gap: 1px;
  font-size: var(--fs-2xs); color: var(--text-3); line-height: 1.5;
}
.bfi-hint-en { color: var(--text-3); opacity: .75; }
</style>
