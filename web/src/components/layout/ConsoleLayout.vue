<template>
  <!-- 完整控制台页面布局。Full console page layout. -->
  <div class="console-page">
    <!-- 控制台顶部栏。Console top header bar. -->
    <header class="console-header">
      <!-- 左侧区域：返回按钮、品牌图标、标题。Left area: back button, brand icon, title. -->
      <div class="ch-left">
        <UiButton variant="secondary" size="sm" @click="router.push('/')">← 开始页</UiButton>
        <span class="ch-crown"><UiIcon name="infinity" :size="13" /></span>
        <span class="ch-title">完整控制台</span>
      </div>
      <!-- 右侧区域：模式开关、状态指示器、清空按钮。Right area: mode switch, status indicator, clear button. -->
      <div class="ch-right">
        <!-- 助手模式开关：对话 = 少打断；任务 = 完成后询问并存档。
             必须放在控制台 —— 这里才是实际跑任务的地方（AppHeader 只在开始页渲染）。
             Assistant mode switch: chat stays out of the way; task asks and archives on
             completion. It belongs here on the console, where tasks actually run
             (AppHeader only renders on the start page). -->
        <div class="ch-mode">
          <button class="ch-mode-item" :class="{ on: assistantMode === 'chat' }" type="button" @click="setAssistantMode('chat')">对话</button>
          <button class="ch-mode-item" :class="{ on: assistantMode === 'task' }" type="button" @click="setAssistantMode('task')">任务</button>
        </div>
        <!-- 助手状态指示。Assistant status indicator. -->
        <span class="ch-state">
          <UiStatusDot :color="asst.stateColor.value" :size="8" :glow="8" />
          {{ asst.stateLabel.value }}
        </span>
        <UiButton variant="secondary" size="sm" hover="danger" @click="emit('clear')">清空</UiButton>
      </div>
    </header>

    <!-- 控制台主体：侧边栏 + 内容区。Console body: sidebar + main content area. -->
    <div class="console-body">
      <ConsoleSidebar :active="active" :wake-enabled="wakeEnabled" @select="emit('select', $event)" />
      <!-- 主内容插槽。Main content slot. -->
      <main class="console-main"><slot /></main>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 控制台页面布局组件，包含顶部栏、侧边栏和主内容区。
 * Console page layout component, contains header bar, sidebar and main content area.
 */
import { useRouter } from 'vue-router'
import { useAssistant } from '../../composables/useAssistant'
import type { ConsoleTabKey } from '../../composables/useConsole'
import { UiButton, UiIcon, UiStatusDot } from '../ui'
import ConsoleSidebar from './ConsoleSidebar.vue'
import { assistantMode, setAssistantMode } from '../../composables/assistant/store'

/** 属性：当前激活的标签页和语音唤醒开关状态。Props: currently active tab key and voice wake toggle state. */
defineProps<{ active: ConsoleTabKey; wakeEnabled: boolean }>()
/** 事件：切换标签页、清空记录。Events: switch tab, clear history. */
const emit = defineEmits<{ select: [key: ConsoleTabKey]; clear: [] }>()

/** 助手组合式函数实例。Assistant composable instance. */
const asst = useAssistant()
/** 路由实例，用于页面跳转。Router instance for page navigation. */
const router = useRouter()
</script>

<style scoped>
.console-page {
  height: 100dvh; min-height: 100vh; overflow: hidden;
  display: flex; flex-direction: column;
  padding-bottom: 120px; /* 避免右下角悬浮球遮挡。Prevent bottom-right floating ball from overlapping. */
  background:
    radial-gradient(1000px 480px at 50% -5%, rgba(103, 232, 249, .06), transparent 60%),
    var(--bg-0);
  color: var(--text-1);
}
.console-header {
  height: var(--header-h); flex-shrink: 0;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 26px;
  background: rgba(2, 6, 23, .8);
  backdrop-filter: blur(10px) saturate(140%);
  -webkit-backdrop-filter: blur(10px) saturate(140%);
  border-bottom: 1px solid var(--border-soft);
  position: sticky; top: 0; z-index: 20;
}
.ch-left { display: flex; align-items: center; gap: 14px; }
.ch-crown {
  width: 26px; height: 26px; border-radius: 8px;
  background: var(--brand-grad); color: var(--text-on-brand);
  display: grid; place-items: center;
}
.ch-title { font-size: var(--fs-md); font-weight: 600; letter-spacing: .04em; }
.ch-right { display: flex; align-items: center; gap: 12px; }
.ch-state { display: inline-flex; align-items: center; gap: 7px; font-size: var(--fs-xs); color: var(--text-2); }

.console-body {
  flex: 1; min-height: 0;
  display: flex; gap: 18px; padding: 18px 22px;
}
.console-main {
  flex: 1; min-width: 0; min-height: 0; overflow: hidden;
  display: flex; flex-direction: column;
}
.ch-mode { display: flex; gap: 2px; background: var(--surface-control); border-radius: var(--r-full); padding: 2px; }
.ch-mode-item { font-size: var(--fs-2xs); color: var(--text-3); background: none; border: none; border-radius: var(--r-full); padding: 3px 10px; cursor: pointer; }
.ch-mode-item.on { color: var(--brand-c2); background: rgba(11, 17, 32, .75); }
</style>
