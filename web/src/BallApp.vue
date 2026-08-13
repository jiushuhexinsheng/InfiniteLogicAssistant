<template>
  <!-- 桌面悬浮小球：80px 圆球，透明窗口内，置顶可拖；单击开控制台，双击开语音 -->
  <div class="desktop-ball" data-tauri-drag-region @click="openConsole" @dblclick="asst.toggleWake()">
    <span class="ring" :style="ringStyle"></span>
    <Icon :name="asst.visual.value.icon" :size="26" />
    <span v-if="asst.wakeEnabled.value" class="mic-badge" title="语音唤醒已开">🎙</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Icon from './components/Icon.vue'
import { useAssistant } from './composables/useAssistant'

const asst = useAssistant()

const ringStyle = computed(() => ({
  borderColor: asst.stateColor.value,
  boxShadow: `0 0 14px ${asst.stateColor.value}`,
  borderWidth: asst.state.value === 'recording' ? '3px' : '2px',
}))

function openConsole() {
  const tauri = (window as any).__TAURI__?.core
  if (tauri?.invoke) {
    tauri.invoke('open_console').catch(() => {
      window.open('/console', '_blank')
    })
  } else {
    window.open('/console', '_blank')
  }
}
</script>

<style scoped>
.desktop-ball {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background: radial-gradient(circle at 35% 30%, #1e293b, #0f172a 70%);
  border: 2px solid #334155;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: grab;
  position: relative;
  user-select: none;
  color: var(--brand-c2);
}
.desktop-ball:active { cursor: grabbing; }
.ring {
  position: absolute;
  inset: -3px;
  border-radius: 50%;
  border: 2px solid var(--brand-c2);
  opacity: .85;
}
.mic-badge {
  position: absolute;
  right: -4px;
  bottom: -4px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #334155;
  font-size: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
