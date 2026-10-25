<template>
  <!-- 回合控制条：回合进行中才出现。暂停 = 挂起执行循环（safe stop 档，LLM 立即停下、
       恢复后续写）；停止 = 取消整个任务（断流 + 后端 stop）。
       Run controls: only while a turn is live. Pause parks the execution loop (safe
       stop: the LLM halts at once and continues on resume); stop cancels the whole
       task (stream abort + backend stop). -->
  <div v-if="turnActive" class="run-controls">
    <UiIconButton
      data-run="pause"
      :title="paused ? '继续' : '暂停'"
      :class="{ 'rc-paused': paused }"
      @click="onToggle"
    ><UiIcon :name="paused ? 'play' : 'pause'" :size="14" /></UiIconButton>
    <UiIconButton data-run="stop" title="停止" variant="danger" @click="onStop">
      <UiIcon name="stop" :size="14" />
    </UiIconButton>
  </div>
</template>

<script setup lang="ts">
import { UiIconButton, UiIcon } from '../ui'
import { abortChat } from '../../composables/assistant/useChat'
import { paused, resetPause, togglePause, turnActive } from '../../composables/assistant/useChatPause'

/** 切换暂停/继续。Toggle pause/resume. */
function onToggle() {
  void togglePause()
}

/** 停止整个回合：断流 + 后端 stop；本地暂停标志一并复位。
 *  Stop the whole turn: abort the stream + backend stop; the local pause flag resets too. */
function onStop() {
  abortChat()
  resetPause()
}
</script>

<style scoped>
/* 控制条：两个图标钮横排，与输入行/头部基线对齐。Two icon buttons in a row. */
.run-controls { display: flex; align-items: center; gap: var(--sp-1); flex-shrink: 0; }
/* 暂停中：播放键用品牌色提示「可继续」。Paused: the play key takes the brand tint. */
.rc-paused { color: var(--brand-c1); }
</style>
