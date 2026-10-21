<!-- 设置字段：统一走 BiFormItem（中文主标签 + 英文副标签 + 控件 + 中英帮助）。
     Settings field: every field goes through BiFormItem so the bilingual layout is consistent. -->
<template>
  <BiFormItem
    :label-zh="label"
    :label-en="en"
    :hint-zh="hint"
    :hint-en="hintEn"
    :row="row"
    :grow="grow"
  >
    <slot />
  </BiFormItem>
</template>

<script setup lang="ts">
import BiFormItem from './BiFormItem.vue'

withDefaults(defineProps<{
  label: string
  en?: string
  hint?: string
  hintEn?: string
  row?: boolean
  grow?: boolean
}>(), {
  en: '',
  hint: '',
  hintEn: '',
  row: false,
  grow: false,
})
</script>
