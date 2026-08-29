<template>
  <span class="ui-status-dot" :style="{ width: size + 'px', height: size + 'px', background: color, boxShadow: glow ? `0 0 ${glow}px ${color}` : undefined }"></span>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ color: string; size?: number; glow?: number }>(), { size: 8, glow: 0 })
</script>

<style scoped>
.ui-status-dot { display: inline-block; border-radius: 50%; flex-shrink: 0; }
</style>
