<template>
  <div class="page">
    <AppHeader />

    <main class="hero">
      <div class="orb-wrap">
        <div class="orb" :class="asst.state.value">
          <span class="orb-halo"></span>
          <span class="orb-ripple"></span>
          <span class="orb-core">
            <UiIcon :name="asst.visual.value.icon" :size="30" />
          </span>
        </div>
        <div class="orb-label">
          <UiStatusDot :color="asst.stateColor.value" :size="7" :glow="8" />
          <span class="mono">{{ asst.stateLabel.value }} · 说「{{ asst.wakeKeyword.value }}」唤醒</span>
        </div>
      </div>

      <h1 class="title">无限逻辑</h1>
      <p class="subtitle">说「{{ asst.wakeKeyword.value }}」唤醒 · 或直接输入文字开聊</p>

      <div class="actions">
        <UiButton variant="primary" @click="asst.expanded.value = true">
          <UiIcon name="messages-square" :size="16" /> 开始对话
        </UiButton>
        <UiButton variant="secondary" @click="asst.toggleWake()">
          <UiIcon :name="asst.wakeEnabled.value ? 'stop' : 'mic'" :size="15" />
          {{ asst.wakeEnabled.value ? '关闭语音唤醒' : '开启语音唤醒' }}
        </UiButton>
        <UiButton variant="ghost" @click="scrollToTts"><UiIcon name="settings" :size="15" /> 语音设置</UiButton>
      </div>

      <div class="cards">
        <UiCard class="start-card" title="实时状态">
          <div class="status-row">
            <div class="live">
              <UiStatusDot :color="asst.stateColor.value" :size="9" :glow="8" />
              <b>{{ asst.stateLabel.value }}</b>
            </div>
            <div class="chips">
              <UiChip :tone="cfg?.llm_available ? 'ok' : 'neutral'" :detail="cfg?.llm_profile || '—'">LLM</UiChip>
              <UiChip :tone="cfg?.asr_available ? 'ok' : 'neutral'" :detail="cfg?.asr_profile || '—'">ASR</UiChip>
              <UiChip :tone="cfg?.tts_available ? 'ok' : 'neutral'" :detail="cfg?.tts_profile || '—'">TTS</UiChip>
              <UiChip :tone="pingOk ? 'ok' : 'neutral'">后端 127.0.0.1:8520</UiChip>
            </div>
          </div>
          <div class="status-foot">
            <span class="mono hint">{{ pingMs != null ? '后端延迟 ' + pingMs + 'ms' : '—' }}</span>
            <UiButton variant="ghost" size="sm" @click="checkPing">刷新</UiButton>
          </div>
          <p v-if="asst.statusLine.value" class="status-detail">{{ asst.statusLine.value }}</p>
        </UiCard>

        <UiCard class="start-card tts-card" title="语音设置">
          <TtsMini />
        </UiCard>
      </div>

      <div class="features">
        <UiCard v-for="f in features" :key="f.title" class="feature" hover>
          <span class="feature-ic"><UiIcon :name="f.icon" :size="18" /></span>
          <div class="feature-body"><h3>{{ f.title }}</h3><p>{{ f.desc }}</p></div>
        </UiCard>
      </div>

      <footer class="page-footer mono">无限逻辑 · 本地优先 AI 助手 — v2.4</footer>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useAssistant } from '../composables/useAssistant'
import { useConfig } from '../composables/useApi'
import { api } from '../api'
import { UiButton, UiCard, UiChip, UiIcon, UiStatusDot } from '../components/ui'
import AppHeader from '../components/layout/AppHeader.vue'
import TtsMini from '../components/assistant/TtsMini.vue'

const asst = useAssistant()
const app = useConfig()

const cfg = computed(() => app.config.value)
const pingOk = ref(false)
const pingMs = ref<number | null>(null)

const features = [
  { icon: 'sparkles', title: '灵感对话', desc: '自然语言直达任务，不必记指令' },
  { icon: 'mic', title: '语音控制', desc: '一句话完成查询、调度与操作' },
  { icon: 'database', title: '记忆常驻', desc: '上下文与偏好长期留存' },
  { icon: 'wrench', title: '工具调用', desc: '挂载 MCP 与系统能力' },
]

function scrollToTts() {
  document.querySelector('.tts-card')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

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

onMounted(async () => {
  if (!app.config.value) await app.initConfig()
  checkPing()
})
</script>

<style scoped>
.page { min-height: 100vh; display: flex; flex-direction: column; user-select: none; }

.hero {
  flex: 1; width: 100%; max-width: 1080px; margin: 0 auto;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 12px; padding: 16px 24px 24px;
}

/* ── 光球 ── */
.orb-wrap { display: flex; flex-direction: column; align-items: center; gap: 10px; }
.orb { position: relative; width: 116px; height: 116px; border-radius: 50%; background: var(--brand-grad); display: grid; place-items: center; box-shadow: var(--glow-brand); }
.orb-halo {
  position: absolute; inset: 10px; border-radius: 50%;
  background: var(--brand-grad); filter: blur(26px); opacity: .45;
  animation: orb-halo 5.5s var(--ease-out) infinite;
}
.orb-ripple {
  position: absolute; inset: 0; border-radius: 50%;
  border: 1.5px solid var(--brand-c2); opacity: .7;
  animation: orb-ripple 3.4s var(--ease-out) infinite;
}
.orb-core {
  position: relative; width: 98px; height: 98px; border-radius: 50%;
  background: var(--bg-1);
  display: grid; place-items: center; color: var(--brand-c1);
}
.orb.listening .orb-ripple { animation-duration: 2s; }
.orb.recording .orb-ripple { animation-duration: 1.3s; }
.orb.recording .orb-core { animation: orb-breathe .7s var(--ease-out) infinite; }
@keyframes orb-breathe { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.05); } }
@keyframes orb-halo { 0%, 100% { opacity: .4; transform: scale(1); } 50% { opacity: .6; transform: scale(1.08); } }
@keyframes orb-ripple { 0% { transform: scale(1); opacity: .7; } 75%, 100% { transform: scale(1.75); opacity: 0; } }

.orb-label {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 5px 12px; border-radius: 999px;
  background: var(--surface-control); border: 1px solid var(--border-soft);
  font-size: var(--fs-xs); color: var(--text-2); letter-spacing: .04em;
}

/* ── 标题 ── */
.title {
  font-size: clamp(2.2rem, 6vw, 3rem); font-weight: 800; letter-spacing: .12em; margin: 0;
  background: linear-gradient(135deg, #c7d2fe 0%, #67e8f9 50%, #6ee7b7 100%);
  -webkit-background-clip: text; background-clip: text; color: transparent;
  filter: drop-shadow(0 0 26px rgba(103, 232, 249, .16));
}
.subtitle { font-size: var(--fs-lg); color: var(--text-2); letter-spacing: .05em; margin: 0; }

/* ── 操作按钮 ── */
.actions { display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; padding-top: 2px; }

/* ── 卡片行 ── */
.cards { display: flex; gap: 12px; flex-wrap: wrap; justify-content: center; width: 100%; padding-top: 4px; }
.start-card { flex: 1 1 440px; max-width: 500px; min-width: 320px; }
.status-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
.live { display: flex; align-items: center; gap: 8px; }
.live b { font-size: var(--fs-sm); font-weight: 600; }
.chips { display: flex; gap: 6px; flex-wrap: wrap; }
.status-foot { display: flex; align-items: center; justify-content: space-between; margin-top: 12px; }
.hint { font-size: var(--fs-2xs); color: var(--text-3); }
.status-detail { font-size: var(--fs-xs); color: var(--err); text-align: center; margin-top: 8px; }

/* ── 语音设置 ── */


/* ── 特性 ── */
.features {
  width: 100%; max-width: 880px;
  display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px;
  padding-top: 6px;
}
.feature { display: flex; gap: 12px; align-items: flex-start; }
.feature-ic {
  width: 36px; height: 36px; flex-shrink: 0; border-radius: var(--r-md);
  display: flex; align-items: center; justify-content: center;
  color: var(--brand-c2); background: rgba(103, 232, 249, .08);
  border: 1px solid rgba(103, 232, 249, .18);
}
.feature h3 { font-size: var(--fs-md); font-weight: 600; margin: 0 0 4px; color: var(--text-1); }
.feature p { font-size: var(--fs-xs); color: var(--text-3); line-height: 1.55; margin: 0; }

/* ── 页脚 ── */
.page-footer { text-align: center; font-size: var(--fs-2xs); color: var(--text-3); letter-spacing: .08em; padding: 2px 0 14px; }

/* ── 入场动效 ── */
.orb-wrap, .title, .subtitle, .actions, .cards, .features {
  animation: rise-in .6s var(--ease-out) both;
}
.orb-wrap { animation-delay: .08s; }
.title { animation-delay: .14s; }
.subtitle { animation-delay: .2s; }
.actions { animation-delay: .26s; }
.cards { animation-delay: .34s; }
.features { animation-delay: .44s; }
@keyframes rise-in { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: translateY(0); } }
</style>
