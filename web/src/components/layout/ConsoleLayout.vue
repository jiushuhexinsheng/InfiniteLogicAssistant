<template>
  <div class="console-page">
    <header class="console-header">
      <div class="ch-left">
        <UiButton variant="secondary" size="sm" @click="router.push('/')">← 开始页</UiButton>
        <span class="ch-crown"><UiIcon name="infinity" :size="13" /></span>
        <span class="ch-title">完整控制台</span>
      </div>
      <div class="ch-right">
        <span class="ch-state">
          <UiStatusDot :color="asst.stateColor.value" :size="8" :glow="8" />
          {{ asst.stateLabel.value }}
        </span>
        <UiButton variant="secondary" size="sm" hover="danger" @click="emit('clear')">清空</UiButton>
      </div>
    </header>

    <div class="console-body">
      <ConsoleSidebar :active="active" :wake-enabled="wakeEnabled" @select="emit('select', $event)" />
      <main class="console-main"><slot /></main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAssistant } from '../../composables/useAssistant'
import type { ConsoleTabKey } from '../../composables/useConsole'
import { UiButton, UiIcon, UiStatusDot } from '../ui'
import ConsoleSidebar from './ConsoleSidebar.vue'

defineProps<{ active: ConsoleTabKey; wakeEnabled: boolean }>()
const emit = defineEmits<{ select: [key: ConsoleTabKey]; clear: [] }>()

const asst = useAssistant()
const router = useRouter()
</script>

<style scoped>
.console-page {
  height: 100dvh; min-height: 100vh; overflow: hidden;
  display: flex; flex-direction: column;
  padding-bottom: 120px; /* 避免右下角悬浮球遮挡 */
  background:
    radial-gradient(1000px 480px at 50% -5%, rgba(103, 232, 249, .06), transparent 60%),
    var(--bg-0);
  color: var(--text-1);
}
.console-header {
  height: var(--header-h); flex-shrink: 0;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 26px;
  background: rgba(2, 6, 23, .8);
  backdrop-filter: blur(10px) saturate(140%);
  -webkit-backdrop-filter: blur(10px) saturate(140%);
  border-bottom: 1px solid var(--border-soft);
  position: sticky; top: 0; z-index: 20;
}
.ch-left { display: flex; align-items: center; gap: 14px; }
.ch-crown {
  width: 26px; height: 26px; border-radius: 8px;
  background: var(--brand-grad); color: var(--text-on-brand);
  display: grid; place-items: center;
}
.ch-title { font-size: var(--fs-md); font-weight: 600; letter-spacing: .04em; }
.ch-right { display: flex; align-items: center; gap: 12px; }
.ch-state { display: inline-flex; align-items: center; gap: 7px; font-size: var(--fs-xs); color: var(--text-2); }

.console-body {
  flex: 1; min-height: 0;
  display: flex; gap: 18px; padding: 18px 22px;
}
.console-main {
  flex: 1; min-width: 0; min-height: 0; overflow: hidden;
  display: flex; flex-direction: column;
}
</style>
