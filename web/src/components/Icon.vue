<template>
  <UiIcon :name="name" :size="size" />
</template>

<script setup lang="ts">
import UiIcon from './ui/UiIcon.vue'
withDefaults(defineProps<{ name: string; size?: number }>(), { size: 18 })
</script>
