<template>
  <div class="console-status">
    <UiCard title="后端连通性">
      <div class="status-row">
        <UiChip :tone="pingOk ? 'ok' : 'err'" detail="127.0.0.1:8520">后端</UiChip>
        <UiButton variant="ghost" size="sm" @click="checkPing">刷新</UiButton>
        <span v-if="pingMs != null" class="ping-ms mono">{{ pingMs }}ms</span>
      </div>
    </UiCard>

    <UiCard title="能力配置（OpenAI 兼容 profile）">
      <div class="status-row">
        <UiChip :tone="cfg?.llm_available ? 'ok' : 'neutral'" :detail="cfg?.llm_profile || '—'">LLM</UiChip>
        <UiChip :tone="cfg?.asr_available ? 'ok' : 'neutral'" :detail="cfg?.asr_profile || '—'">ASR</UiChip>
        <UiChip :tone="cfg?.tts_available ? 'ok' : 'neutral'" :detail="cfg?.tts_profile || '—'">TTS(后端)</UiChip>
      </div>
      <p class="hint">语音播报实际走浏览器 SpeechSynthesis；「TTS」徽章表示后端可选 TTS 配置能力，两者相互独立。</p>
    </UiCard>

    <UiCard title="唤醒词与静音检测（VAD）">
      <div class="kv">
        <template v-if="ww">
          <span>唤醒词</span><b>{{ ww.keyword }}</b>
          <span>灵敏度</span><b>{{ ww.sensitivity }}</b>
          <span>模型</span><b class="mono">{{ ww.model_path }}</b>
        </template>
        <template v-if="vad">
          <span>静音阈值</span><b>{{ vad.silence_threshold }}</b>
          <span>静音时长</span><b>{{ vad.silence_duration_ms }} ms</b>
          <span>最长录音</span><b>{{ vad.max_duration_ms }} ms</b>
        </template>
        <template v-if="!ww && !vad"><span>—</span><b>未加载配置</b></template>
      </div>
    </UiCard>

    <UiCard title="当前助手状态">
      <div class="status-row">
        <UiStatusDot :color="asst.stateColor.value" :size="9" :glow="8" />
        <b>{{ asst.stateLabel.value }}</b>
        <span class="muted">{{ asst.wakeEnabled.value ? '语音唤醒已开启' : '语音唤醒未开启' }}</span>
      </div>
      <p v-if="asst.statusLine.value" class="hint">{{ asst.statusLine.value }}</p>
    </UiCard>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api } from '../../api'
import { useAssistant } from '../../composables/useAssistant'
import { useConfig } from '../../composables/useApi'
import { UiButton, UiCard, UiChip, UiStatusDot } from '../ui'

const asst = useAssistant()
const app = useConfig()

const cfg = computed(() => app.config.value)
const ww = computed(() => cfg.value?.wake_word)
const vad = computed(() => cfg.value?.vad)

const pingOk = ref(false)
const pingMs = ref<number | null>(null)
let timer: ReturnType<typeof setInterval> | null = null

async function checkPing() {
  try {
    const t0 = performance.now()
    const r = await api.ping()
    pingMs.value = Math.round(performance.now() - t0)
    pingOk.value = r.ok === true
  } catch {
    pingOk.value = false
    pingMs.value = null
  }
}

onMounted(() => {
  if (!app.config.value) app.initConfig()
  checkPing()
  timer = setInterval(checkPing, 15000)
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.console-status { max-width: 720px; width: 100%; margin: 0 auto; display: flex; flex-direction: column; gap: 12px; }
.status-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.status-row .muted { color: var(--text-3); font-size: 12px; }
.ping-ms { font-size: 11px; color: var(--text-3); }
.hint { font-size: 11px; color: var(--text-3); margin-top: 8px; line-height: 1.6; }
.kv { display: grid; grid-template-columns: 92px 1fr; gap: 8px 12px; font-size: 12px; }
.kv span { color: var(--text-3); }
.kv b { color: var(--text-1); font-weight: 500; word-break: break-all; }
</style>
