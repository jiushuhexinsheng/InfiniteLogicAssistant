<template>
  <!-- 卡2（本地）：浏览器语音设置。即时保存 localStorage，无需「保存」按钮。
       Card 2 (local): browser voice settings. Instant localStorage save, no "Save" button. -->
  <UiCard class="cs-card">
    <div class="cs-card-head">
      <span class="cs-card-title">本地语音 · 浏览器合成</span>
      <span class="cs-card-note">改动即时生效（存本机）</span>
    </div>
    <TtsSettings />
  </UiCard>
</template>

<script setup lang="ts">
/**
 * 本地语音配置卡（两卡堆叠的卡2 · 本地分支）。
 * Local voice config card (second of the two stacked cards, local branch).
 */
import { UiCard } from '../../ui'
import TtsSettings from '../../assistant/TtsSettings.vue'
</script>

<style scoped>
.cs-card { display: flex; flex-direction: column; gap: 12px; }
.cs-card-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.cs-card-title { font-size: var(--fs-sm); font-weight: 600; color: var(--text-1); letter-spacing: .02em; }
.cs-card-note { font-size: var(--fs-2xs); color: var(--text-3); }
</style>
