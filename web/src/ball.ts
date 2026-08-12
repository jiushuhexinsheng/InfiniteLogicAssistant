import { createApp } from 'vue'
import BallApp from './BallApp.vue'
import { useConfig } from './composables/useApi'
import { useAssistant } from './composables/useAssistant'
import './styles/assistant.css'

const app = createApp(BallApp)

// 桌面悬浮球独立入口：初始化配置 + 助手（不开路由）
const cfg = useConfig()
const asst = useAssistant()
cfg.initConfig().then(() => {
  asst.init({
    wake: cfg.config.value?.wake_word,
    vad: cfg.config.value?.vad,
  })
})

app.mount('#app')
