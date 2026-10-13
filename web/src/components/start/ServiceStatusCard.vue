<template>
  <StartCard title="实时状态">
    <template #badge>
      <span class="status-badge" :style="{ background: asst.stateColor.value }">{{ asst.stateLabel.value }}</span>
    </template>

    <div class="service-grid">
      <div class="service-item">
        <span class="service-name">LLM</span>
        <span class="service-status" :class="{ ok: cfg?.llm_available }">{{ cfg?.llm_profile || '未配置' }}</span>
      </div>
      <div class="service-item">
        <span class="service-name">ASR</span>
        <span class="service-status" :class="{ ok: cfg?.asr_available }">{{ cfg?.asr_profile || '未配置' }}</span>
      </div>
      <div class="service-item">
        <span class="service-name">TTS</span>
        <span class="service-status" :class="{ ok: cfg?.tts_available }">{{ cfg?.tts_profile || '未配置' }}</span>
      </div>
      <div class="service-item">
        <span class="service-name">后端</span>
        <span class="service-status" :class="{ ok: pingOk }">{{ pingMs != null ? pingMs + 'ms' : '未连接' }}</span>
      </div>
    </div>
    <UiButton variant="secondary" size="sm" block @click="checkPing" aria-label="刷新连接状态">刷新状态</UiButton>
  </StartCard>
</template>

<!-- 起始页「实时状态」卡：能力配置一览 + 后端 ping。
     Start-page "实时状态" card: capability summary plus the backend ping.

     ping 逻辑随卡一起搬进来，并抽到 `composables/usePing`（与控制台「状态」页共用同一实现 ——
     两处原本逐行相同）。
     配置的拉取仍留在 StartPage —— `cfg` 是响应式的，晚到也会自动重渲染。
     The ping moved in with the card and on into `composables/usePing` (shared with the console's
     状态 tab — the two were line-for-line identical).
     Config fetching stays in StartPage — `cfg` is reactive, so a late arrival simply re-renders. -->
<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useAssistant } from '../../composables/useAssistant'
import { useConfig } from '../../composables/useApi'
import { usePing } from '../../composables/usePing'
import StartCard from './StartCard.vue'
import { UiButton } from '../ui'

const asst = useAssistant()
const app = useConfig()
const cfg = computed(() => app.config.value)

/** 后端连通性探测。Backend reachability probe. */
const { pingOk, pingMs, checkPing } = usePing()

onMounted(() => { checkPing() })
</script>

<style scoped>
.status-badge {
  padding: var(--sp-1) var(--sp-3);
  border-radius: var(--r-full);
  font-size: var(--fs-xs);
  color: var(--text-on-brand);
  font-weight: 500;
}

.service-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--sp-3);
}

.service-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--sp-2) var(--sp-3);
  background: var(--bg-2);
  border-radius: var(--r-md);
}

.service-name {
  font-size: var(--fs-sm);
  color: var(--text-2);
  font-weight: 500;
}

.service-status {
  font-size: var(--fs-xs);
  color: var(--text-3);
}

.service-status.ok {
  color: var(--ok);
}
</style>
