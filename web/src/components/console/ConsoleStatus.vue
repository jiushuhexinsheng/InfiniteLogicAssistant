<template>
  <div class="console-status">
    <!-- 后端连通性 -->
    <div class="card">
      <div class="card-title">后端连通性</div>
      <div class="status-row">
        <StatusChip label="后端" :available="pingOk" detail="127.0.0.1:8520" />
        <button class="mini-btn" @click="checkPing">刷新</button>
        <span v-if="pingMs != null" class="ping-ms">{{ pingMs }}ms</span>
      </div>
    </div>

    <!-- 能力配置 -->
    <div class="card">
      <div class="card-title">能力配置（OpenAI 兼容 profile）</div>
      <div class="status-row">
        <StatusChip label="LLM" :available="!!cfg?.llm_available" :detail="cfg?.llm_profile" />
        <StatusChip label="ASR" :available="!!cfg?.asr_available" :detail="cfg?.asr_profile" />
        <StatusChip label="TTS(后端)" :available="!!cfg?.tts_available" :detail="cfg?.tts_profile" />
      </div>
      <p class="hint">语音播报实际走浏览器 SpeechSynthesis；「TTS」徽章表示后端可选 TTS 配置能力，两者相互独立。</p>
    </div>

    <!-- 唤醒词与 VAD -->
    <div class="card">
      <div class="card-title">唤醒词与静音检测（VAD）</div>
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
    </div>

    <!-- 当前助手状态 -->
    <div class="card">
      <div class="card-title">当前助手状态</div>
      <div class="status-row">
        <span class="dot" :style="{ background: asst.stateColor.value }"></span>
        <b>{{ asst.stateLabel.value }}</b>
        <span class="muted">{{ asst.wakeEnabled.value ? '语音唤醒已开启' : '语音唤醒未开启' }}</span>
      </div>
      <p v-if="asst.statusLine.value" class="hint">{{ asst.statusLine.value }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api } from '../../api'
import { useAssistant } from '../../composables/useAssistant'
import { useConfig } from '../../composables/useApi'
import StatusChip from './StatusChip.vue'

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
.console-status { max-width: 720px; width: 100%; margin: 0 auto; }

.status-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.status-row .dot { width: 9px; height: 9px; border-radius: 50%; }
.status-row .muted { color: var(--text-3); font-size: 12px; }

.mini-btn {
  background: none;
  border: 1px solid var(--border-base);
  color: var(--text-2);
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 999px;
  cursor: pointer;
}
.mini-btn:hover { color: var(--brand-c2); border-color: var(--brand-c2); }
.ping-ms { font-size: 11px; color: var(--text-3); }

.hint { font-size: 11px; color: var(--text-3); margin: 8px 0 0; line-height: 1.6; }

.kv {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 6px 14px;
  font-size: 12px;
}
.kv span { color: var(--text-3); }
.kv b { color: var(--text-1); font-weight: 500; }
.kv .mono { font-family: ui-monospace, Consolas, monospace; font-size: 11px; word-break: break-all; }
</style>
