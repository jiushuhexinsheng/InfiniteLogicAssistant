<template>
  <div class="page">
    <div class="hero">
      <h1 class="title">无限逻辑 · 语音助手</h1>
      <p class="subtitle">唤醒词：{{ asst.wakeKeyword.value }}</p>
      <p class="desc">悬浮球常驻右下角 —— 说"{{ asst.wakeKeyword.value }}"唤醒，或直接输入文字即可开始对话</p>
    </div>

    <div class="actions">
      <button class="btn primary" @click="asst.expanded.value = true">开始对话</button>
      <button class="btn" @click="asst.toggleWake()">
        {{ asst.wakeEnabled.value ? '关闭语音唤醒' : '开启语音唤醒' }}
      </button>
      <button class="btn" @click="router.push('/console')">打开完整控制台 →</button>
    </div>

    <div class="state-line" :style="{ color: asst.stateColor.value }">
      当前状态：{{ asst.stateLabel.value }}
    </div>

    <div class="status">
      <StatusChip label="LLM" :available="!!cfg?.llm_available" :detail="cfg?.llm_profile" />
      <StatusChip label="ASR" :available="!!cfg?.asr_available" :detail="cfg?.asr_profile" />
      <StatusChip label="TTS" :available="!!cfg?.tts_available" :detail="cfg?.tts_profile" />
      <StatusChip label="后端" :available="pingOk" detail="127.0.0.1:8520" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAssistant } from '../composables/useAssistant'
import { useConfig } from '../composables/useApi'
import { api } from '../api'
import StatusChip from '../components/console/StatusChip.vue'

const asst = useAssistant()
const app = useConfig()
const router = useRouter()

const cfg = computed(() => app.config.value)
const pingOk = ref(false)

onMounted(async () => {
  if (!app.config.value) await app.initConfig()
  try {
    const r = await api.ping()
    pingOk.value = r.ok === true
  } catch { pingOk.value = false }
})
</script>

<style scoped>
.page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: safe center; /* 内容超高时改为顶对齐，避免裁剪 */
  gap: 28px;
  background: radial-gradient(ellipse at top, #1e293b 0%, #0f172a 60%, #020617 100%);
  color: #e2e8f0;
  overflow-y: auto;
  user-select: none;
  padding: 40px 24px;
}
.hero { text-align: center; pointer-events: none; }
.title {
  font-size: clamp(2rem, 6vw, 3.2rem);
  font-weight: 700;
  letter-spacing: 0.04em;
  margin: 0 0 0.75rem;
  background: linear-gradient(135deg, #a5b4fc 0%, #67e8f9 50%, #6ee7b7 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.subtitle {
  font-size: clamp(0.95rem, 2vw, 1.15rem);
  color: #94a3b8;
  margin: 0;
  letter-spacing: 0.35em;
}
.desc { font-size: 13px; color: #64748b; margin-top: 10px; }

.actions { display: flex; gap: 12px; flex-wrap: wrap; justify-content: center; }
.btn {
  border: 1px solid var(--border-base);
  background: rgba(30, 41, 59, .7);
  color: var(--text-1);
  font-size: 14px;
  padding: 9px 20px;
  border-radius: 999px;
  cursor: pointer;
  transition: border-color .15s, transform .1s, box-shadow .15s;
}
.btn:hover { border-color: var(--brand-c2); box-shadow: 0 0 14px rgba(103, 232, 249, .18); }
.btn:active { transform: scale(.97); }
.btn.primary {
  background: var(--brand-grad);
  border-color: transparent;
  color: #0f172a;
  font-weight: 600;
}

.state-line { font-size: 13px; opacity: .9; }

.status { display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; }
</style>
