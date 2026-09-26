<template>
  <div class="page">
    <AppHeader />

    <main class="hero">
      <!-- 光球动画区域 -->
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
          <span class="mono">{{ asst.stateLabel.value }} · 说{{ asst.wakeHint.value }}唤醒</span>
        </div>
      </div>

      <!-- 标题 -->
      <h1 class="title">无限逻辑</h1>
      <p class="subtitle">说{{ asst.wakeHint.value }}唤醒 · 或直接输入文字开聊</p>

      <!-- 操作按钮 -->
      <div class="actions">
        <UiButton variant="primary" @click="asst.expanded.value = true" aria-label="开始对话">
          <UiIcon name="messages-square" :size="16" /> 开始对话
        </UiButton>
        <UiButton variant="secondary" @click="asst.toggleWake()" :aria-label="asst.wakeEnabled.value ? '关闭语音唤醒' : '开启语音唤醒'">
          <UiIcon :name="asst.wakeEnabled.value ? 'stop' : 'mic'" :size="15" />
          {{ asst.wakeEnabled.value ? '关闭语音唤醒' : '开启语音唤醒' }}
        </UiButton>
        <UiButton variant="ghost" @click="scrollToTts" aria-label="语音设置">
          <UiIcon name="settings" :size="15" /> 语音设置
        </UiButton>
      </div>

      <!-- 状态卡片 -->
      <div class="cards">
        <div class="card">
          <div class="card-header">
            <span class="card-title">实时状态</span>
            <span class="status-badge" :style="{ background: asst.stateColor.value }">{{ asst.stateLabel.value }}</span>
          </div>
          <div class="card-body">
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
            <button class="btn-refresh" @click="checkPing" aria-label="刷新连接状态">刷新状态</button>
          </div>
        </div>

        <div class="card tts-card">
          <div class="card-header">
            <span class="card-title">语音设置</span>
          </div>
          <div class="card-body">
            <TtsMini />
          </div>
        </div>
      </div>

      <!-- 功能特性 -->
      <section class="features" aria-label="功能特性">
        <div v-for="f in features" :key="f.title" class="feature-item">
          <span class="feature-icon">{{ f.icon }}</span>
          <div class="feature-content">
            <h2 class="feature-title">{{ f.title }}</h2>
            <p class="feature-desc">{{ f.desc }}</p>
          </div>
        </div>
      </section>

      <!-- 页脚 -->
      <footer class="page-footer">无限逻辑 · 本地优先 AI 助手 — v2.4</footer>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useAssistant } from '../composables/useAssistant'
import { useConfig } from '../composables/useApi'
import { api } from '../api'
import { UiButton, UiIcon, UiStatusDot } from '../components/ui'
import AppHeader from '../components/layout/AppHeader.vue'
import TtsMini from '../components/assistant/TtsMini.vue'

const asst = useAssistant()
const app = useConfig()
const cfg = computed(() => app.config.value)
const pingOk = ref(false)
const pingMs = ref<number | null>(null)

const features = [
  { icon: '✨', title: '灵感对话', desc: '自然语言直达任务，不必记指令' },
  { icon: '🎤', title: '语音控制', desc: '一句话完成查询、调度与操作' },
  { icon: '💾', title: '记忆常驻', desc: '上下文与偏好长期留存' },
  { icon: '🔧', title: '工具调用', desc: '挂载 MCP 与系统能力' },
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
.page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.hero {
  flex: 1;
  width: 100%;
  max-width: 960px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--sp-6);
  padding: var(--sp-8) var(--sp-5);
}

/* ── 光球 ── */
.orb-wrap { display: flex; flex-direction: column; align-items: center; gap: 10px; }
.orb {
  position: relative; width: 116px; height: 116px; border-radius: 50%;
  background: var(--brand-grad); display: grid; place-items: center;
}
.orb-halo {
  position: absolute; inset: 10px; border-radius: 50%;
  background: var(--brand-grad); filter: blur(26px); opacity: .45;
  animation: orb-halo 5.5s ease-in-out infinite;
}
.orb-ripple {
  position: absolute; inset: 0; border-radius: 50%;
  border: 1.5px solid var(--brand-c2); opacity: .7;
  animation: orb-ripple 3.4s ease-out infinite;
}
.orb-core {
  position: relative; width: 98px; height: 98px; border-radius: 50%;
  background: var(--bg-1);
  display: grid; place-items: center; color: var(--brand-c1);
}
.orb.listening .orb-ripple { animation-duration: 2s; }
.orb.recording .orb-ripple { animation-duration: 1.3s; }
.orb.recording .orb-core { animation: orb-breathe .7s ease-in-out infinite; }
@keyframes orb-breathe { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.05); } }
@keyframes orb-halo { 0%, 100% { opacity: .4; transform: scale(1); } 50% { opacity: .6; transform: scale(1.08); } }
@keyframes orb-ripple { 0% { transform: scale(1); opacity: .7; } 75%, 100% { transform: scale(1.75); opacity: 0; } }

.orb-label {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 6px 12px; border-radius: 999px;
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

.subtitle {
  font-size: var(--fs-lg); color: var(--text-2); letter-spacing: .05em; margin: 0;
  line-height: 1.5;
}

/* ── 操作按钮 ── */
.actions { display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; padding-top: 2px; }

/* ── 卡片 ── */
.cards {
  display: flex;
  gap: var(--sp-4);
  flex-wrap: wrap;
  justify-content: center;
  width: 100%;
}

.card {
  flex: 1 1 400px;
  max-width: 480px;
  background: var(--bg-1);
  border: 1px solid var(--border-base);
  border-radius: var(--r-xl);
  overflow: hidden;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--sp-4);
  border-bottom: 1px solid var(--border-base);
}

.card-title {
  font-size: var(--fs-md);
  font-weight: 600;
  color: var(--text-1);
}

.status-badge {
  padding: var(--sp-1) var(--sp-3);
  border-radius: var(--r-full);
  font-size: var(--fs-xs);
  color: var(--text-on-brand);
  font-weight: 500;
}

.card-body {
  padding: var(--sp-4);
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

.btn-refresh {
  width: 100%;
  margin-top: var(--sp-3);
  padding: var(--sp-2);
  background: var(--bg-2);
  border: 1px solid var(--border-base);
  border-radius: var(--r-md);
  color: var(--text-2);
  font-size: var(--fs-xs);
  cursor: pointer;
}

.btn-refresh:hover {
  background: var(--surface-control-hover);
  color: var(--text-1);
}

/* ── 功能特性 ── */
.features {
  width: 100%;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--sp-3);
}

.feature-item {
  display: flex;
  gap: var(--sp-3);
  padding: var(--sp-4);
  background: var(--bg-1);
  border: 1px solid var(--border-base);
  border-radius: var(--r-lg);
}

.feature-icon {
  font-size: 24px;
  flex-shrink: 0;
}

.feature-content {
  min-width: 0;
}

.feature-title {
  font-size: var(--fs-md);
  font-weight: 600;
  color: var(--text-1);
  margin-bottom: var(--sp-1);
  margin-top: 0;
}

.feature-desc {
  font-size: var(--fs-xs);
  color: var(--text-3);
  line-height: 1.5;
}

/* ── 页脚 ── */
.page-footer {
  text-align: center;
  font-size: var(--fs-xs);
  color: var(--text-3);
  padding: var(--sp-6) 0;
  line-height: 1.5;
}

/* ── 入场动效（仅上半部分） ── */
.orb-wrap, .title, .subtitle, .actions {
  animation: rise-in .6s ease-out both;
}
.orb-wrap { animation-delay: .08s; }
.title { animation-delay: .14s; }
.subtitle { animation-delay: .2s; }
.actions { animation-delay: .26s; }
@keyframes rise-in { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: translateY(0); } }
</style>
