<template>
  <div class="console-page">
    <header class="console-header">
      <button class="back-btn" @click="router.push('/')">← 开始页</button>
      <span class="title">完整控制台</span>
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
      <ConsoleMemoryView v-else />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAssistant } from '../composables/useAssistant'
import ConsoleConversation from '../components/console/ConsoleConversation.vue'
import ConsoleTaskView from '../components/console/ConsoleTaskView.vue'
import ConsoleStatus from '../components/console/ConsoleStatus.vue'
import ConsoleTools from '../components/console/ConsoleTools.vue'
import ConsoleStats from '../components/console/ConsoleStats.vue'
import ConsoleEnvView from '../components/console/ConsoleEnvView.vue'
import ConsoleMemoryView from '../components/console/ConsoleMemoryView.vue'

const asst = useAssistant()
const router = useRouter()

type TabKey = 'conv' | 'task' | 'status' | 'tools' | 'stats' | 'env' | 'memory'
const tabs: { key: TabKey; label: string }[] = [
  { key: 'conv', label: '对话' },
  { key: 'task', label: '任务' },
  { key: 'status', label: '状态' },
  { key: 'tools', label: '工具' },
  { key: 'stats', label: '统计' },
  { key: 'env', label: '环境' },
  { key: 'memory', label: '记忆' },
]
const activeTab = ref<TabKey>('conv')
</script>
