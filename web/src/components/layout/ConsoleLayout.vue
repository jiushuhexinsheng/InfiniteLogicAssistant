<template>
  <!-- 完整控制台页面布局（顶栏由 App.vue 壳层的 AppHeader 统一提供）。
       Full console page layout (the top bar comes from AppHeader in the App.vue shell). -->
  <div class="console-page">
    <!-- 控制台主体：侧边栏 + 内容区。Console body: sidebar + main content area. -->
    <div class="console-body">
      <ConsoleSidebar
        :active="active"
        :wake-enabled="wakeEnabled"
        @select="emit('select', $event)"
      />
      <!-- 主内容插槽。Main content slot. -->
      <main class="console-main"><slot /></main>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 控制台页面布局组件：侧边栏 + 主内容区。顶栏（导航、系统信息、「返回开始页」）
 * 由 App.vue 的 AppHeader 统一渲染；「新建/清空对话」在对话页左上
 * （2026-10-11 用户裁定，不进菜单）。
 * Console layout: sidebar + main. The header (nav, system info, back to start) is
 * rendered once by AppHeader in App.vue; "New/Clear conversation" sits on the
 * conversation page's top-left (2026-10-11 user ruling — not in the menu).
 */
import type { ConsoleTabKey } from '../../composables/useConsole'
import ConsoleSidebar from './ConsoleSidebar.vue'

/** 属性：当前激活的标签页和语音唤醒开关状态。Props: currently active tab key and voice wake toggle state. */
defineProps<{ active: ConsoleTabKey; wakeEnabled: boolean }>()
/** 事件：切换标签页。Events: switch tab. */
const emit = defineEmits<{ select: [key: ConsoleTabKey] }>()
</script>

<style scoped>
.console-page {
  height: 100%; min-height: 0; overflow: hidden;
  display: flex; flex-direction: column;
  padding-bottom: var(--sp-q120); /* 避免右下角悬浮球遮挡。Prevent bottom-right floating ball from overlapping. */
  background:
    radial-gradient(1000px 480px at 50% -5%, rgba(103, 232, 249, .06), transparent 60%),
    var(--bg-0);
  color: var(--text-1);
}

.console-body {
  flex: 1; min-height: 0;
  display: flex; gap: var(--sp-q18); padding: var(--sp-q18) var(--sp-q22);
}
.console-main {
  flex: 1; min-width: 0; min-height: 0; overflow: hidden;
  display: flex; flex-direction: column;
}
</style>
