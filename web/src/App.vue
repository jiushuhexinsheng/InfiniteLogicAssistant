<!-- 应用根组件模板 -->
<!-- Application root component template -->
<template>
  <!-- 全站布局壳：统一导航栏 + 路由视图。Site layout shell: shared header + router view. -->
  <div class="app-shell">
    <AppHeader />
    <div class="app-view">
      <!-- 路由视图，渲染当前路由对应的组件 -->
      <!-- Router view, renders component matching current route -->
      <router-view />
    </div>
  </div>
  <!-- 悬浮球全局常驻（跨路由），Teleport 到 body -->
  <!-- Floating assistant globally persistent (cross-route), Teleported to body -->
  <FloatingAssistant :asst="asst" />
  <!-- 全局通知浮层（错误 / 成功提示） -->
  <!-- Global notification overlay (error / success notices) -->
  <UiToaster />
</template>

<!-- 应用根组件脚本 -->
<!-- Application root component script -->
<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import FloatingAssistant from './components/FloatingAssistant.vue'
import AppHeader from './components/layout/AppHeader.vue'
import { UiToaster } from './components/ui'
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
  // 构建标记：F12 Console 若看不到此行 = 页面还在跑旧 JS（关标签页重开，普通刷新可能拿到缓存的旧模块图）。
  // Build marker: absent in F12 Console = the page still runs stale JS (close the tab and reopen; a plain refresh may reuse the cached old module graph).
  console.info('%c[ILA] build 2026-09-29-r2', 'color:#22d3ee;font-weight:bold')
  // 初始化配置 / Initialize configuration
  await app.initConfig()
  // 初始化助手，传入唤醒词、VAD 和通话模式配置
  // Initialize assistant, pass wake word, VAD and call-mode config
  asst.init({
    wake: app.config.value?.wake_word,
    vad: app.config.value?.vad,
    call: app.config.value?.call,
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

<style scoped>
/* 全站布局壳：顶栏常驻，内容区独立滚动。Site shell: sticky-height header, scrolling content area. */
.app-shell {
  height: 100dvh;
  display: flex;
  flex-direction: column;
}
.app-view {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}
</style>
