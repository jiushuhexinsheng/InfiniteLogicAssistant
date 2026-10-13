<template>
  <!-- 卡2（本地）：浏览器语音设置。即时保存 localStorage，无需「保存」按钮。
       Card 2 (local): browser voice settings. Instant localStorage save, no "Save" button. -->
  <SettingsCard title="本地语音 · 浏览器合成">
    <template #actions>
      <span class="cs-card-note">改动即时生效（存本机）</span>
    </template>

    <TtsSettings />
  </SettingsCard>
</template>

<script setup lang="ts">
/**
 * 本地语音配置卡（两卡堆叠的卡2 · 本地分支）。
 * Local voice config card (second of the two stacked cards, local branch).
 */
import SettingsCard from './SettingsCard.vue'
import TtsSettings from '../../assistant/TtsSettings.vue'
</script>

<style scoped>
/* 卡头右侧说明文字。Note text on the right of the card head. */
.cs-card-note { font-size: var(--fs-2xs); color: var(--text-3); }
</style>
