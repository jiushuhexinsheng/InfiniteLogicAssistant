<template>
  <div class="console-conv">
    <!-- 顶部左侧动作条：新建 + 清空并排（2026-10-11 用户裁定：放对话页左侧，不进菜单）。
         Top-left action bar: New + Clear side by side (2026-10-11 user ruling: on the
         conversation page's left, not in the menu). -->
    <div class="conv-top">
      <UiButton variant="secondary" size="sm" @click="newSession">
        <UiIcon name="plus" :size="13" /> 新建对话
      </UiButton>
      <UiButton variant="secondary" size="sm" hover="danger" @click="asst.clearMessages()">
        <UiIcon name="trash" :size="13" /> 清空对话
      </UiButton>
    </div>
    <ConsoleMessageList
      :messages="asst.messages.value"
      :can-act="canAct"
      @retry="asst.retryTool($event)"
      @cancel="asst.cancelTool($event)"
      @fork="onFork"
      @edit="onEdit"
      @regen="onRegen"
    />
    <div class="console-input">
      <ChatInput :disabled="false" @send="onSend" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useAssistant } from '../../composables/useAssistant'
import { useConsole } from '../../composables/useConsole'
import { state, currentSessionId } from '../../composables/assistant/store'
import { notify } from '../../composables/useToast'
import ConsoleMessageList from './ConsoleMessageList.vue'
import ChatInput from '../assistant/ChatInput.vue'
import { UiButton, UiIcon } from '../ui'

/** 当前助手实例，提供消息列表、发送文本等能力。Current assistant instance providing messages, sendText, etc. */
const asst = useAssistant()

/** 新建会话（逻辑在 useConsole，2026-10-11 随按钮迁回对话页顶左）。
 *  New conversation (logic lives in useConsole; moved back to the page's top-left on 2026-10-11). */
const { newSession } = useConsole()

/** 消息级动作开关：回合空闲（done/error/idle）且已关联服务端会话（docs/designs/07 约束）。
 *  Message-level actions enabled only when idle and bound to a server session. */
const canAct = computed(() =>
  (state.value === 'done' || state.value === 'error' || state.value === 'idle')
  && !!currentSessionId.value)

/** 处理用户发送消息：将文本转发给助手。Handle user send: forward text to the assistant. */
function onSend(text: string) {
  asst.sendText(text)
}

/** 分叉：成功后提示（原会话保留，历史列表可见新分叉线）。 */
async function onFork(index: number) {
  const ok = await asst.forkAt(index)
  if (ok) notify.ok('已从处分叉到新会话（原会话保留）')
  else notify.err('分叉失败（回合进行中或无会话）')
}

/** 编辑用户消息并重发（非末条自动先分叉保原路径）。 */
async function onEdit(index: number, text: string) {
  const ok = await asst.sendEdited(index, text)
  if (!ok) notify.err('编辑重发失败（回合进行中或无会话）')
}

/** 重新生成助手回复（分叉到原问题后重跑）。 */
async function onRegen(index: number) {
  const ok = await asst.regenerate(index)
  if (!ok) notify.err('重新生成失败（回合进行中或无会话）')
}
</script>

<style scoped>
.console-conv { flex: 1; min-height: 0; display: flex; flex-direction: column; gap: var(--sp-3); }
/* 动作条固定在左上（不随消息滚动）。Action bar pinned top-left (does not scroll with messages). */
.conv-top {
  display: flex; justify-content: flex-start; gap: var(--sp-2);
  padding: 2px 4px 0;
  position: relative; z-index: 5;
}
.console-input { max-width: 880px; width: 100%; margin: 0 auto; padding-bottom: var(--sp-2); }
</style>
