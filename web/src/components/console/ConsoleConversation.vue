<template>
  <div class="console-conv">
    <!-- 右上角浮动「新建会话」：顶部固定，消息滚动时不滚走。Floating "New Session" button at top-right: fixed at top, won't scroll away with messages. -->
    <div class="conv-top">
      <UiButton variant="secondary" size="sm" @click="newSession">＋ 新建会话</UiButton>
    </div>
    <ConsoleMessageList
      :messages="asst.messages.value"
      :wake-hint="asst.wakeHint.value"
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
import { api } from '../../api'
import { useAssistant } from '../../composables/useAssistant'
import { createNewSession, state, currentSessionId } from '../../composables/assistant/store'
import { notify } from '../../composables/useToast'
import { formatError } from '../../errors'
import ConsoleMessageList from './ConsoleMessageList.vue'
import ChatInput from '../assistant/ChatInput.vue'
import { UiButton } from '../ui'

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

/** 新建会话：清空当前对话，开启新的独立对话线。Create a new session: clear current conversation and start a fresh independent thread. */
async function newSession() {
  try {
    const r = await api.createSession()
    createNewSession(r.session.id)
    notify.ok('已新建会话')
  } catch (e) {
    notify.err('新建会话失败：' + formatError(e))
  }
}
</script>

<style scoped>
.console-conv { flex: 1; min-height: 0; display: flex; flex-direction: column; gap: 12px; }
.conv-top {
  /* 顶部固定浮动：不随消息滚动。Fixed floating at top: does not scroll with messages. */
  display: flex; justify-content: flex-end;
  padding: 2px 4px 0;
  position: relative; z-index: 5;
}
.console-input { max-width: 880px; width: 100%; margin: 0 auto; padding-bottom: 8px; }
</style>
