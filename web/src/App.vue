<template>
  <div class="page">
    <div class="hero">
      <h1 class="title">无限逻辑 · 语音助手</h1>
      <p class="subtitle">唤醒词：小逻小逻</p>
    </div>
    <FloatingAssistant :asst="asst" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'

import FloatingAssistant from './components/FloatingAssistant.vue'
import { useConfig } from './composables/useApi'
import { useAssistant } from './composables/useAssistant'

const app = useConfig()
const asst = useAssistant()

onMounted(async () => {
  await app.initConfig()
  asst.init()
})

onUnmounted(() => {
  asst.destroy()
})
</script>

<style scoped>
.page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: radial-gradient(ellipse at top, #1e293b 0%, #0f172a 60%, #020617 100%);
  color: #e2e8f0;
  overflow: hidden;
  user-select: none;
}
.hero {
  text-align: center;
  pointer-events: none;
}
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
</style>
