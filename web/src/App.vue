<template>
  <router-view />
  <!-- 悬浮球全局常驻（跨路由），Teleport 到 body -->
  <FloatingAssistant :asst="asst" />
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import FloatingAssistant from './components/FloatingAssistant.vue'
import { useConfig } from './composables/useApi'
import { useAssistant } from './composables/useAssistant'

const app = useConfig()
const asst = useAssistant()

function teardown() {
  asst.destroy()
}

onMounted(async () => {
  await app.initConfig()
  asst.init({
    wake: app.config.value?.wake_word,
    vad: app.config.value?.vad,
  })
  window.addEventListener('beforeunload', teardown)
})

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', teardown)
  teardown()
})
</script>
