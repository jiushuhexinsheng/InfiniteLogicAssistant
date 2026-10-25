<template>
  <!-- 链路方向箭头：品牌色圆形徽章 + chevron，横/纵两种方向。 -->
  <span class="chain-arrow" :class="direction" aria-hidden="true">
    <UiIcon :name="direction === 'down' ? 'arrow-down' : 'chevron-right'" :size="12" />
  </span>
</template>

<script setup lang="ts">
/** 链路箭头（纯展示）。Chain direction arrow. */
import { UiIcon } from '../../ui'

withDefaults(defineProps<{ direction?: 'right' | 'down' }>(), { direction: 'right' })
</script>

<style scoped>
.chain-arrow {
  display: inline-flex; align-items: center; justify-content: center;
  width: 20px; height: 20px; border-radius: 50%;
  color: var(--brand-c2);
  border: 1px solid rgba(103, 232, 249, .35);
  background: rgba(103, 232, 249, .08);
  box-shadow: 0 0 8px rgba(103, 232, 249, .18);
}
.chain-arrow.down { color: #67e8f9; }
</style>
