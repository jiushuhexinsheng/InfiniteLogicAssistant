<!-- 控制台页面模板 / Console page template -->
<template>
  <!-- 控制台布局组件，包含标签页切换和消息清除功能 / Console layout component with tab switching and message clearing -->
  <ConsoleLayout :active="activeTab" :wake-enabled="asst.wakeEnabled.value" @select="activeTab = $event" @clear="asst.clearMessages()">
    <!-- 对话标签页 / Conversation tab -->
    <ConsoleConversation v-if="activeTab === 'conv'" />
    <!-- 任务标签页 / Task tab -->
    <ConsoleTaskView v-else-if="activeTab === 'task'" />
    <!-- 状态标签页 / Status tab -->
    <ConsoleStatus v-else-if="activeTab === 'status'" />
    <!-- 工具标签页 / Tools tab -->
    <ConsoleTools v-else-if="activeTab === 'tools'" />
    <!-- 统计标签页 / Stats tab -->
    <ConsoleStats v-else-if="activeTab === 'stats'" />
    <!-- 环境标签页 / Environment tab -->
    <ConsoleEnvView v-else-if="activeTab === 'env'" />
    <!-- 记忆标签页 / Memory tab -->
    <ConsoleMemoryView v-else-if="activeTab === 'memory'" />
    <!-- 设置标签页 / Settings tab -->
    <ConsoleSettings v-else-if="activeTab === 'settings'" />
    <!-- 历史标签页 / History tab -->
    <ConsoleHistory v-else-if="activeTab === 'history'" />
    <!-- 任务库标签页 / Task-library tab -->
    <ConsoleLibrary v-else-if="activeTab === 'library'" />
    <!-- 调度标签页（默认） / Schedule tab (default) -->
    <ConsoleScheduleView v-else />
  </ConsoleLayout>
</template>

<!-- 控制台页面脚本 / Console page script -->
<script setup lang="ts">
/**
 * 控制台页面组件 - 管理多个标签页的异步加载和切换
 * Console page component - manages async loading and switching of multiple tabs
 */
import { defineAsyncComponent } from 'vue'
import { useAssistant } from '../composables/useAssistant'
import { useConsole } from '../composables/useConsole'
import ConsoleLayout from '../components/layout/ConsoleLayout.vue'
/**
 * 默认「对话」tab 静态引入（首屏即渲染）；其余 tab 异步加载，减小初始包
 * Default "conversation" tab is statically imported (renders on first screen); other tabs are async loaded to reduce initial bundle size
 */
import ConsoleConversation from '../components/console/ConsoleConversation.vue'

/** 异步加载任务视图组件 / Async load task view component */
const ConsoleTaskView = defineAsyncComponent(() => import('../components/console/ConsoleTaskView.vue'))
/** 异步加载状态组件 / Async load status component */
const ConsoleStatus = defineAsyncComponent(() => import('../components/console/ConsoleStatus.vue'))
/** 异步加载工具组件 / Async load tools component */
const ConsoleTools = defineAsyncComponent(() => import('../components/console/ConsoleTools.vue'))
/** 异步加载统计组件 / Async load stats component */
const ConsoleStats = defineAsyncComponent(() => import('../components/console/ConsoleStats.vue'))
/** 异步加载环境视图组件 / Async load environment view component */
const ConsoleEnvView = defineAsyncComponent(() => import('../components/console/ConsoleEnvView.vue'))
/** 异步加载记忆视图组件 / Async load memory view component */
const ConsoleMemoryView = defineAsyncComponent(() => import('../components/console/ConsoleMemoryView.vue'))
/** 异步加载设置组件 / Async load settings component */
const ConsoleSettings = defineAsyncComponent(() => import('../components/console/ConsoleSettings.vue'))
/** 异步加载调度视图组件 / Async load schedule view component */
const ConsoleScheduleView = defineAsyncComponent(() => import('../components/console/ConsoleScheduleView.vue'))
/** 异步加载任务库视图组件 / Async load task-library view component */
const ConsoleLibrary = defineAsyncComponent(() => import('../components/console/ConsoleLibrary.vue'))
/** 异步加载历史组件 / Async load history component */
const ConsoleHistory = defineAsyncComponent(() => import('../components/console/ConsoleHistory.vue'))

/** 获取助手实例 / Get assistant instance */
const asst = useAssistant()
/** 获取控制台状态和激活标签页 / Get console state and active tab */
const { activeTab } = useConsole()
</script>
