<template>
  <!-- 图标组件，透传 name 和 size 到 UiIcon。Icon component, passes name and size through to UiIcon. -->
  <UiIcon :name="name" :size="size" />
</template>

<script setup lang="ts">
/**
 * 简化图标封装组件，对 UiIcon 进行薄封装。
 * Simplified icon wrapper component, a thin wrapper around UiIcon.
 */
import UiIcon from './ui/UiIcon.vue'
/** 属性：图标名称和可选尺寸（默认 18px）。Props: icon name and optional size (default 18px). */
withDefaults(defineProps<{ name: string; size?: number }>(), { size: 18 })
</script>
