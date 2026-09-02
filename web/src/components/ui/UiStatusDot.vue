<template>
  <span class="ui-status-dot" :style="{ width: size + 'px', height: size + 'px', background: color, boxShadow: glow ? `0 0 ${glow}px ${color}` : undefined }"></span>
</template>

<!-- 状态圆点组件，纯展示，用于表示连接/运行等状态。Status dot indicator for connection/activity state display. -->
<script setup lang="ts">
/** 状态圆点 Props：颜色值/直径(像素)/光晕半径(0 表示无光晕)。StatusDot props: color value, diameter in px, glow radius (0 = no glow). */
withDefaults(defineProps<{ color: string; size?: number; glow?: number }>(), { size: 8, glow: 0 })
</script>

<style scoped>
.ui-status-dot { display: inline-block; border-radius: 50%; flex-shrink: 0; }
</style>
