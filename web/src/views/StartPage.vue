<template>
  <div class="page">
    <!-- 品牌标 -->
    <header class="brand">
      <span class="brand-mark"><Icon name="infinity" :size="18" /></span>
      <span class="brand-name">无限逻辑</span>
      <span class="brand-sub">VOICE · OMNICONTROL</span>
    </header>

    <!-- 签名：状态响应的渐变球（助手"在场"的化身） -->
    <div class="orb" :class="asst.state.value" :style="{ '--orb-color': asst.stateColor.value }">
      <span class="orb-halo"></span>
      <span class="orb-ripple"></span>
      <span class="orb-core">
        <Icon :name="asst.visual.value.icon" :size="34" />
      </span>
      <span class="orb-label">{{ asst.stateLabel.value }}</span>
    </div>

    <main class="hero">
      <h1 class="title">无限逻辑</h1>
      <p class="subtitle">说「{{ asst.wakeKeyword.value }}」唤醒 · 或直接输入文字开聊</p>
    </main>

    <div class="actions">
      <button class="btn btn-primary" @click="asst.expanded.value = true">
        <Icon name="messages-square" :size="16" /> 开始对话
      </button>
      <button class="btn btn-secondary" @click="asst.toggleWake()">
        <Icon :name="asst.wakeEnabled.value ? 'stop' : 'mic'" :size="15" />
        {{ asst.wakeEnabled.value ? '关闭语音唤醒' : '开启语音唤醒' }}
      </button>
      <button class="btn btn-secondary" @click="scrollToTts">
        <Icon name="settings" :size="15" /> 语音设置
      </button>
      <button class="btn btn-ghost" @click="router.push('/console')">
        打开完整控制台 <Icon name="chevron-down" :size="14" class="chev" />
      </button>
    </div>

    <!-- 实时状态玻璃卡 -->
    <section class="status-card glass-card">
      <div class="status-head">
        <span class="eyebrow">系统状态</span>
        <span class="status-live mono" :style="{ color: asst.stateColor.value }">
          <i class="live-dot"></i>{{ asst.stateLabel.value }}
        </span>
      </div>
      <div class="chips">
        <span class="chip" :class="cfg?.llm_available ? 'on' : 'off'"><i class="chip-dot"></i>LLM {{ cfg?.llm_profile || '—' }}</span>
        <span class="chip" :class="cfg?.asr_available ? 'on' : 'off'"><i class="chip-dot"></i>ASR {{ cfg?.asr_profile || '—' }}</span>
        <span class="chip" :class="cfg?.tts_available ? 'on' : 'off'"><i class="chip-dot"></i>TTS {{ cfg?.tts_profile || '—' }}</span>
        <span class="chip" :class="pingOk ? 'on' : 'off'"><i class="chip-dot"></i>后端 127.0.0.1:8520</span>
      </div>
      <p v-if="asst.statusLine.value" class="status-detail">{{ asst.statusLine.value }}</p>
    </section>

    <!-- 语音设置 -->
    <section class="tts-card">
      <div class="tts-card-head">
        <span class="tts-card-title"><Icon name="settings" :size="15" /> 语音设置</span>
        <span class="tts-card-desc">调节播报音量 / 语速 / 声音 · 自动记住</span>
      </div>
      <TtsSettings />
    </section>

    <!-- 能力特性 -->
    <section class="features">
      <div class="feature glass-card">
        <span class="feature-ic"><Icon name="mic" :size="18" /></span>
        <div class="feature-body"><h3>语音对话</h3><p>说"{{ asst.wakeKeyword.value }}"唤醒，或直接打字开聊</p></div>
      </div>
      <div class="feature glass-card">
        <span class="feature-ic"><Icon name="zap" :size="18" /></span>
        <div class="feature-body"><h3>联网工具</h3><p>查天气、对时间、搜索，交给小逻</p></div>
      </div>
      <div class="feature glass-card">
        <span class="feature-ic"><Icon name="database" :size="18" /></span>
        <div class="feature-body"><h3>持续记忆</h3><p>记住你的偏好，对话不重来</p></div>
      </div>
      <div class="feature glass-card">
        <span class="feature-ic"><Icon name="calendar-clock" :size="18" /></span>
        <div class="feature-body"><h3>定时任务</h3><p>到点自动执行，无需值守</p></div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAssistant } from '../composables/useAssistant'
import { useConfig } from '../composables/useApi'
import { api } from '../api'
import Icon from '../components/Icon.vue'
import TtsSettings from '../components/assistant/TtsSettings.vue'

const asst = useAssistant()
const app = useConfig()
const router = useRouter()

const cfg = computed(() => app.config.value)
const pingOk = ref(false)

// 「语音设置」入口按钮 → 平滑滚到设置卡片
function scrollToTts() {
  document.querySelector('.tts-card')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

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
  justify-content: safe center;
  gap: 26px;
  padding: 36px 24px 72px;
  overflow-y: auto;
  user-select: none;
}

/* ── 品牌标 ── */
.brand { display: flex; align-items: center; gap: 10px; }
.brand-mark {
  width: 34px; height: 34px; border-radius: var(--r-md);
  display: flex; align-items: center; justify-content: center;
  background: var(--brand-grad); color: #0f172a;
  box-shadow: var(--glow-brand);
}
.brand-name { font-size: var(--fs-lg); font-weight: 700; letter-spacing: .08em; }
.brand-sub { font-size: var(--fs-2xs); color: var(--text-3); font-family: var(--font-mono); letter-spacing: .2em; margin-top: 1px; }

/* ── 签名球 ── */
.orb {
  position: relative;
  width: 180px; height: 186px;
  display: flex; align-items: center; justify-content: center;
}
.orb-core {
  position: relative; z-index: 2;
  width: 96px; height: 96px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center; color: #0f172a;
  background:
    radial-gradient(circle at 32% 28%, rgba(255, 255, 255, .85), transparent 42%),
    var(--brand-grad);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, .1), var(--glow-brand);
  animation: orb-breathe 4.5s var(--ease-out) infinite;
}
.orb-halo {
  position: absolute; inset: 10px; border-radius: 50%;
  background: var(--brand-grad); filter: blur(26px); opacity: .45;
  animation: orb-halo 5.5s var(--ease-out) infinite;
}
.orb-ripple {
  position: absolute; inset: 0; border-radius: 50%;
  border: 1.5px solid var(--orb-color, var(--brand-c2));
  opacity: .7;
  animation: orb-ripple 3.4s var(--ease-out) infinite;
}
.orb-label {
  position: absolute; bottom: 0; left: 50%; transform: translateX(-50%);
  font-size: var(--fs-xs); font-family: var(--font-mono); letter-spacing: .08em;
  color: var(--text-2); white-space: nowrap;
}
/* 聆听/录音：涟漪加速、呼吸更紧，呼应"活着"的状态 */
.orb.listening .orb-ripple { animation-duration: 2s; }
.orb.listening .orb-core { animation-duration: 2.6s; }
.orb.recording .orb-ripple { animation-duration: 1.3s; }
.orb.recording .orb-core { animation: orb-breathe .7s var(--ease-out) infinite; }
@keyframes orb-breathe {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.05); }
}
@keyframes orb-halo {
  0%, 100% { opacity: .4; transform: scale(1); }
  50% { opacity: .6; transform: scale(1.08); }
}
@keyframes orb-ripple {
  0% { transform: scale(1); opacity: .7; }
  75%, 100% { transform: scale(1.75); opacity: 0; }
}

/* ── 标题 ── */
.hero { display: flex; flex-direction: column; align-items: center; gap: 12px; text-align: center; }
.title {
  font-size: clamp(2.4rem, 7vw, 4rem);
  font-weight: 800; letter-spacing: .12em; margin: 0;
  background: linear-gradient(135deg, #c7d2fe 0%, #67e8f9 50%, #6ee7b7 100%);
  -webkit-background-clip: text; background-clip: text; color: transparent;
  filter: drop-shadow(0 0 26px rgba(103, 232, 249, .16));
}
.subtitle { font-size: var(--fs-lg); color: var(--text-2); letter-spacing: .05em; margin: 0; }

/* ── 操作按钮 ── */
.actions { display: flex; gap: 12px; flex-wrap: wrap; justify-content: center; }
.chev { transform: rotate(-90deg); }

/* ── 状态玻璃卡 ── */
.status-card {
  width: min(520px, 92vw);
  padding: 18px 22px;
  display: flex; flex-direction: column; gap: 14px;
}
.status-head { display: flex; align-items: center; justify-content: space-between; }
.status-live {
  display: inline-flex; align-items: center; gap: 7px;
  font-size: var(--fs-xs); letter-spacing: .04em;
}
.live-dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; box-shadow: 0 0 8px currentColor; animation: live-blink 2s ease-in-out infinite; }
@keyframes live-blink { 0%, 100% { opacity: 1; } 50% { opacity: .35; } }
.chips { display: flex; flex-wrap: wrap; gap: 8px; }
.status-detail { font-size: var(--fs-xs); color: var(--err); text-align: center; }

/* ── 语音设置 ── */
.tts-card {
  width: min(520px, 92vw);
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.tts-card-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.tts-card-title {
  display: inline-flex; align-items: center; gap: 7px;
  font-size: var(--fs-md); font-weight: 600; color: var(--text-1);
  letter-spacing: .02em;
}
.tts-card-title :deep(svg) { color: var(--brand-c2); }
.tts-card-desc { font-size: var(--fs-2xs); color: var(--text-3); }

/* ── 能力特性 ── */
.features {
  width: min(880px, 94vw);
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 14px;
}
.feature {
  display: flex; gap: 12px; align-items: flex-start;
  padding: 16px 18px;
  transition: transform var(--dur-base) var(--ease-out), border-color var(--dur-base), box-shadow var(--dur-base);
}
.feature:hover { transform: translateY(-3px); border-color: rgba(103, 232, 249, .35); box-shadow: var(--shadow-3); }
.feature-ic {
  width: 36px; height: 36px; flex-shrink: 0; border-radius: var(--r-md);
  display: flex; align-items: center; justify-content: center;
  color: var(--brand-c2); background: rgba(103, 232, 249, .08);
  border: 1px solid rgba(103, 232, 249, .18);
}
.feature h3 { font-size: var(--fs-md); font-weight: 600; margin: 0 0 4px; color: var(--text-1); }
.feature p { font-size: var(--fs-xs); color: var(--text-3); line-height: 1.55; margin: 0; }

/* ── 入场动效（stagger） ── */
.brand, .orb, .hero, .actions, .status-card, .tts-card, .feature {
  animation: rise-in .6s var(--ease-out) both;
}
.brand { animation-delay: .02s; }
.orb { animation-delay: .08s; }
.hero { animation-delay: .14s; }
.actions { animation-delay: .2s; }
.status-card { animation-delay: .26s; }
.tts-card { animation-delay: .32s; }
.feature:nth-child(1) { animation-delay: .38s; }
.feature:nth-child(2) { animation-delay: .44s; }
.feature:nth-child(3) { animation-delay: .5s; }
.feature:nth-child(4) { animation-delay: .56s; }
@keyframes rise-in {
  from { opacity: 0; transform: translateY(16px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
