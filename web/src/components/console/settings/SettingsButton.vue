<template>
  <!-- 设置页统一动作按钮：中文主标签 + 英文副标签，尺寸/形状/危险色保持一致。
       Unified settings action button: Chinese primary + English secondary label,
       consistent size/shape/danger styling. -->
  <span class="settings-action-wrap">
    <UiButton
      class="settings-action"
      :variant="variant"
      :size="size"
      :hover="hover"
      :shape="shape"
      :disabled="disabled"
      :loading="loading"
    >
      <UiIcon v-if="icon" :name="icon" :size="12" />
      <BiLabel :zh="zh" :en="en" layout="stack" />
    </UiButton>
  </span>
</template>

<script setup lang="ts">
/** 统一动作按钮（双语）。Settings action button with bilingual label. */
import BiLabel from './BiLabel.vue'
import { UiButton, UiIcon } from '../../ui'

withDefaults(defineProps<{
  zh: string
  en?: string
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md' | 'lg'
  hover?: 'brand' | 'danger'
  shape?: 'pill' | 'square'
  disabled?: boolean
  loading?: boolean
  icon?: string
}>(), {
  en: '',
  variant: 'secondary',
  size: 'sm',
  hover: 'brand',
  shape: 'pill',
  disabled: false,
  loading: false,
  icon: '',
})

</script>

<style scoped>
.settings-action-wrap { display: inline-flex; }
.settings-action :deep(.bi-label) { align-items: center; }
.settings-action :deep(.bi-en) { opacity: .75; }
</style>
