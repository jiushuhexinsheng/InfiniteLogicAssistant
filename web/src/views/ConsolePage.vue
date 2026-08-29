<template>
  <ConsoleLayout :active="activeTab" :wake-enabled="asst.wakeEnabled.value" @select="activeTab = $event" @clear="asst.clearMessages()">
    <ConsoleConversation v-if="activeTab === 'conv'" />
    <ConsoleTaskView v-else-if="activeTab === 'task'" />
    <ConsoleStatus v-else-if="activeTab === 'status'" />
    <ConsoleTools v-else-if="activeTab === 'tools'" />
    <ConsoleStats v-else-if="activeTab === 'stats'" />
    <ConsoleEnvView v-else-if="activeTab === 'env'" />
    <ConsoleMemoryView v-else-if="activeTab === 'memory'" />
    <ConsoleSettings v-else-if="activeTab === 'settings'" />
    <ConsoleHistory v-else-if="activeTab === 'history'" />
    <ConsoleScheduleView v-else />
  </ConsoleLayout>
</template>

<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import { useAssistant } from '../composables/useAssistant'
import { useConsole } from '../composables/useConsole'
import ConsoleLayout from '../components/layout/ConsoleLayout.vue'
// 默认「对话」tab 静态引入（首屏即渲染）；其余 tab 异步加载，减小初始包
import ConsoleConversation from '../components/console/ConsoleConversation.vue'

const ConsoleTaskView = defineAsyncComponent(() => import('../components/console/ConsoleTaskView.vue'))
const ConsoleStatus = defineAsyncComponent(() => import('../components/console/ConsoleStatus.vue'))
const ConsoleTools = defineAsyncComponent(() => import('../components/console/ConsoleTools.vue'))
const ConsoleStats = defineAsyncComponent(() => import('../components/console/ConsoleStats.vue'))
const ConsoleEnvView = defineAsyncComponent(() => import('../components/console/ConsoleEnvView.vue'))
const ConsoleMemoryView = defineAsyncComponent(() => import('../components/console/ConsoleMemoryView.vue'))
const ConsoleSettings = defineAsyncComponent(() => import('../components/console/ConsoleSettings.vue'))
const ConsoleScheduleView = defineAsyncComponent(() => import('../components/console/ConsoleScheduleView.vue'))
const ConsoleHistory = defineAsyncComponent(() => import('../components/console/ConsoleHistory.vue'))

const asst = useAssistant()
const { activeTab } = useConsole()
</script>
