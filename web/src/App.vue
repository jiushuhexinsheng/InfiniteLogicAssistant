<!-- 应用根组件模板 -->
<!-- Application root component template -->
<template>
  <!-- 路由视图，渲染当前路由对应的组件 -->
  <!-- Router view, renders component matching current route -->
  <router-view />
  <!-- 悬浮球全局常驻（跨路由），Teleport 到 body -->
  <!-- Floating assistant globally persistent (cross-route), Teleported to body -->
  <FloatingAssistant :asst="asst" />
</template>

<!-- 应用根组件脚本 -->
<!-- Application root component script -->
<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import FloatingAssistant from './components/FloatingAssistant.vue'
import { useConfig } from './composables/useApi'
import { useAssistant } from './composables/useAssistant'

// 初始化配置管理 / Initialize config management
const app = useConfig()
// 初始化助手管理 / Initialize assistant management
const asst = useAssistant()

/**
 * 清理函数，销毁助手实例
 * Cleanup function, destroy assistant instance
 */
function teardown() {
  asst.destroy()
}

// 组件挂载时初始化 / Initialize on component mount
onMounted(async () => {
  // 初始化配置 / Initialize configuration
  await app.initConfig()
  // 初始化助手，传入唤醒词和 VAD 配置
  // Initialize assistant, pass wake word and VAD config
  asst.init({
    wake: app.config.value?.wake_word,
    vad: app.config.value?.vad,
  })
  // 监听页面卸载事件 / Listen for page unload event
  window.addEventListener('beforeunload', teardown)
})

// 组件卸载前清理 / Cleanup before component unmount
onBeforeUnmount(() => {
  // 移除页面卸载事件监听 / Remove page unload event listener
  window.removeEventListener('beforeunload', teardown)
  // 执行清理函数 / Execute cleanup function
  teardown()
})
</script>
