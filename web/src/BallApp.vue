<template>
  <!-- 桌面悬浮球小部件：球头(拖拽) + 迷你历史 + 输入；无路由，常驻 -->
  <div class="widget">
    <div class="widget-head" data-tauri-drag-region>
      <span class="ball-icon" data-tauri-drag-region>
        <Icon :name="asst.visual.value.icon" :size="16" />
        <span class="ball-ring" :style="{ borderColor: asst.stateColor.value }"></span>
      </span>
      <span class="widget-title" data-tauri-drag-region>小逻 · {{ asst.stateLabel.value }}</span>
      <button class="icon-btn" :title="asst.wakeEnabled.value ? '关闭语音唤醒' : '开启语音唤醒'" @click="asst.toggleWake()">
        {{ asst.wakeEnabled.value ? '🎙' : '🎤' }}
      </button>
      <button class="icon-btn" title="打开完整控制台" @click="openConsole">⧉</button>
    </div>

    <MiniHistory
      class="widget-body"
      :messages="asst.messages.value"
      :state="asst.state.value"
      :visual="asst.visual.value"
      :wake-keyword="asst.wakeKeyword.value"
      @select="openConsole"
    />

    <div class="widget-input">
      <ChatInput :disabled="false" @send="asst.sendText" />
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from './components/Icon.vue'
import MiniHistory from './components/assistant/MiniHistory.vue'
import ChatInput from './components/assistant/ChatInput.vue'
import { useAssistant } from './composables/useAssistant'

const asst = useAssistant()

function openConsole() {
  // 桌面壳内由 Tauri 打开控制台窗口；兜底打开浏览器
  if ((window as any).__TAURI__?.core?.invoke) {
    ;(window as any).__TAURI__.core.invoke('open_console')
  } else {
    window.open('/console', '_blank')
  }
}
</script>

<style scoped>
.widget {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: linear-gradient(var(--panel-bg), var(--panel-bg)) padding-box,
    var(--brand-grad) border-box;
  border: 1px solid transparent;
  border-radius: 14px;
  overflow: hidden;
  box-shadow: 0 8px 32px rgba(0, 0, 0, .5);
  padding: 2px;
}
.widget-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  cursor: grab;
  user-select: none;
  border-bottom: 1px solid var(--border-base);
}
.ball-icon { position: relative; display: inline-flex; }
.ball-icon :deep(.icon) { color: var(--brand-c2); }
.ball-ring {
  position: absolute;
  inset: -4px;
  border-radius: 50%;
  border: 2px solid var(--brand-c2);
  opacity: .7;
}
.widget-title {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  color: var(--text-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.icon-btn {
  background: none;
  border: none;
  color: var(--text-2);
  font-size: 14px;
  cursor: pointer;
  padding: 2px 4px;
}
.icon-btn:hover { color: var(--brand-c2); }
.widget-body { flex: 1; min-height: 0; overflow-y: auto; padding: 8px; }
.widget-input { padding: 8px 10px 10px; border-top: 1px solid var(--border-base); }
</style>
