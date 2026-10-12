<template>
  <div class="console-conv">
    <!-- 「新建会话」已移至左侧栏（与「清空」并排，2026-10-11 用户要求）。
         "New Session" moved to the left sidebar (beside "Clear", 2026-10-11 user request). -->
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
import { state, currentSessionId } from '../../composables/assistant/store'
import { notify } from '../../composables/useToast'
import ConsoleMessageList from './ConsoleMessageList.vue'
import ChatInput from '../assistant/ChatInput.vue'

/** 当前助手实例，提供消息列表、发送文本等能力。Current assistant instance providing messages, sendText, etc. */
const asst = useAssistant()

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
.console-conv { flex: 1; min-height: 0; display: flex; flex-direction: column; gap: 12px; }
.console-input { max-width: 880px; width: 100%; margin: 0 auto; padding-bottom: 8px; }
</style>
