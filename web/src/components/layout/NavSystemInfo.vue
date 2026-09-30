<template>
  <!-- 导航栏右侧系统信息胶囊：状态 + 模型 + 唤醒词（非交互，随视口宽度分段隐藏）。
       Header system-info pill: state + model + wake word (non-interactive, segments hide on narrow viewports). -->
  <div class="nsi" role="group" aria-label="系统状态">
    <span class="nsi-seg nsi-state">
      <UiStatusDot :color="asst.stateColor.value" :size="7" :glow="8" />
      <span class="nsi-text">{{ asst.stateLabel.value }}</span>
    </span>
    <span class="nsi-sep" aria-hidden="true">·</span>
    <span class="nsi-seg nsi-model" title="当前 LLM 模型">
      <span class="nsi-label">模型</span>
      <span class="nsi-text">{{ cfg?.llm_profile || '未配置' }}</span>
    </span>
    <span class="nsi-sep nsi-sep-model" aria-hidden="true">·</span>
    <span class="nsi-seg nsi-wake" :title="asst.wakeHint.value">
      <span class="nsi-label">唤醒词</span>
      <span class="nsi-text nsi-text-clamp">{{ asst.wakeHint.value }}</span>
    </span>
  </div>
</template>

<script setup lang="ts">
/**
 * 导航栏右侧紧凑系统信息组件。
 * Compact system-info component for the header's right side.
 *
 * 用 div 而非 button —— 全局 button { min-height:44px } 会撑爆 56px 顶栏；
 * 不用 aria-live —— stateLabel 在听/录时高频变化会刷屏读屏器。
 * Uses div not button (global 44px min-height would overflow the header);
 * no aria-live (stateLabel changes rapidly while listening/recording).
 */
import { computed } from 'vue'
import { useConfig } from '../../composables/useApi'
import { useAssistant } from '../../composables/useAssistant'
import { UiStatusDot } from '../ui'

/** 助手组合式函数实例。Assistant composable instance. */
const asst = useAssistant()
/** 全局配置（单飞加载）。Global config (single-flight loaded). */
const app = useConfig()
/** 当前配置响应。Current config response. */
const cfg = computed(() => app.config.value)
</script>

<style scoped>
.nsi {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-1) var(--sp-3);
  background: var(--bg-2);
  border: 1px solid var(--border-base);
  border-radius: var(--r-full);
  font-size: var(--fs-xs);
  color: var(--text-2);
  white-space: nowrap;
  min-width: 0;
}
.nsi-seg {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.nsi-label {
  color: var(--text-3);
  font-size: var(--fs-xs);
}
.nsi-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.nsi-text-clamp { max-width: 16em; }
.nsi-sep { color: var(--text-3); }

/* 分段隐藏：小屏依次收起模型、唤醒词。Progressive segment hiding on narrow viewports. */
@media (max-width: 900px) {
  .nsi-model,
  .nsi-sep-model { display: none; }
}
@media (max-width: 640px) {
  /* 模型（900px 已隐藏）与唤醒词都收起后，仅剩状态段——两个分隔符都要收，
     否则会留下悬空的 "·"。With model already hidden, only the state segment
     remains — drop both separators to avoid a dangling "·". */
  .nsi-wake,
  .nsi-sep,
  .nsi-sep-model { display: none; }
}
</style>
