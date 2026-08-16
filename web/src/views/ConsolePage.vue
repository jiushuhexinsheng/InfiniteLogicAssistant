<template>
  <div class="console-page">
    <header class="console-header">
      <button class="back-btn" @click="router.push('/')">← 开始页</button>
      <span class="title"><span class="crown"><Icon name="infinity" :size="13" /></span>完整控制台</span>
      <span class="head-state">
        <span class="dot" :style="{ background: asst.stateColor.value }"></span>
        {{ asst.stateLabel.value }}
      </span>
      <button class="clear-btn" @click="asst.clearMessages()">清空</button>
    </header>

    <nav class="console-tabs">
      <button
        v-for="t in tabs"
        :key="t.key"
        class="console-tab"
        :class="{ active: activeTab === t.key }"
        @click="activeTab = t.key"
      >
        {{ t.label }}
      </button>
    </nav>

    <div class="console-panel">
      <ConsoleConversation v-if="activeTab === 'conv'" />
      <ConsoleTaskView v-else-if="activeTab === 'task'" />
      <ConsoleStatus v-else-if="activeTab === 'status'" />
      <ConsoleTools v-else-if="activeTab === 'tools'" />
      <ConsoleStats v-else-if="activeTab === 'stats'" />
      <ConsoleEnvView v-else-if="activeTab === 'env'" />
      <ConsoleMemoryView v-else-if="activeTab === 'memory'" />
      <ConsoleSettings v-else-if="activeTab === 'settings'" />
      <ConsoleScheduleView v-else />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, defineAsyncComponent } from 'vue'
import { useRouter } from 'vue-router'
import { useAssistant } from '../composables/useAssistant'
import Icon from '../components/Icon.vue'
// 默认「对话」tab 静态引入（首屏即渲染）；其余 tab 用到时才异步加载，减小控制台初始包
import ConsoleConversation from '../components/console/ConsoleConversation.vue'
const ConsoleTaskView = defineAsyncComponent(() => import('../components/console/ConsoleTaskView.vue'))
const ConsoleStatus = defineAsyncComponent(() => import('../components/console/ConsoleStatus.vue'))
const ConsoleTools = defineAsyncComponent(() => import('../components/console/ConsoleTools.vue'))
const ConsoleStats = defineAsyncComponent(() => import('../components/console/ConsoleStats.vue'))
const ConsoleEnvView = defineAsyncComponent(() => import('../components/console/ConsoleEnvView.vue'))
const ConsoleMemoryView = defineAsyncComponent(() => import('../components/console/ConsoleMemoryView.vue'))
const ConsoleSettings = defineAsyncComponent(() => import('../components/console/ConsoleSettings.vue'))
const ConsoleScheduleView = defineAsyncComponent(() => import('../components/console/ConsoleScheduleView.vue'))

const asst = useAssistant()
const router = useRouter()

type TabKey = 'conv' | 'task' | 'status' | 'tools' | 'stats' | 'env' | 'memory' | 'settings' | 'schedule'
const tabs: { key: TabKey; label: string }[] = [
  { key: 'conv', label: '对话' },
  { key: 'task', label: '任务' },
  { key: 'status', label: '状态' },
  { key: 'tools', label: '工具' },
  { key: 'stats', label: '统计' },
  { key: 'env', label: '环境' },
  { key: 'memory', label: '记忆' },
  { key: 'settings', label: '设置' },
  { key: 'schedule', label: '定时' },
]
const activeTab = ref<TabKey>('conv')
</script>
