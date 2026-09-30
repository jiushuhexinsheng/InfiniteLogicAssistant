<template>
  <!-- 单条消息项，按角色（user/assistant/system）区分样式。Single message item, styled by role (user/assistant/system). -->
  <div class="msg-item" :class="message.role">
    <!-- 头像（系统消息不显示）。Avatar (hidden for system messages). -->
    <span v-if="message.role !== 'system'" class="msg-avatar" :class="message.role">
      <UiIcon :name="message.role === 'assistant' ? 'brain' : 'user'" :size="14" />
    </span>
    <div class="msg-body">
      <!-- 消息元信息：角色名 + 时间戳。Message meta: role name + timestamp. -->
      <div class="msg-meta">
        <span class="msg-role">{{ roleName }}</span>
        <span class="msg-time">{{ formatTime(message.timestamp) }}</span>
      </div>
      <!-- 消息气泡：块宿主按注册协议渲染（思考/工具/正文/提问/汇总等模块）。
           无块的旧消息退化为文本投影渲染（过渡期保护）。
           Message bubble: the block host renders via the registry protocol
           (thinking / tool / text / question / summary modules). Messages without
           blocks degrade to the text projection (transition guard). -->
      <div class="msg-bubble" :class="message.role">
        <BlockHost
          v-if="message.blocks?.length"
          :blocks="message.blocks"
          skin="full"
          @retry="emit('retry', $event)"
          @cancel="emit('cancel', $event)"
        />
        <template v-else>
          <MarkdownRenderer v-if="message.role !== 'system'" :text="message.text" />
          <div v-else class="msg-text">{{ message.text }}</div>
        </template>
      </div>
      <!-- 消息级操作（docs/designs/07）：hover 出现；编辑仅 user、重新生成仅 assistant、
           分叉两者皆可。回合进行中/无会话时由父级把 canAct 置 false 禁用。
           Message-level actions (docs/designs/07): show on hover; edit is user-only,
           regenerate is assistant-only, fork is for both. The parent sets canAct=false
           while a turn runs or when there is no session. -->
      <div v-if="canAct && message.role !== 'system'" class="msg-actions">
        <template v-if="message.role === 'user'">
          <button v-if="!editing" type="button" class="ma-btn" @click="startEdit">编辑</button>
          <button type="button" class="ma-btn" @click="emit('fork', props.index)">分叉</button>
        </template>
        <template v-else-if="message.role === 'assistant'">
          <button type="button" class="ma-btn" @click="emit('regen', props.index)">重新生成</button>
          <button type="button" class="ma-btn" @click="emit('fork', props.index)">分叉</button>
        </template>
      </div>
      <!-- 内联编辑（docs/designs/07）：保存 → emit edit(index, text)；取消还原。
           Inline edit: save emits edit(index, text); cancel reverts. -->
      <div v-if="editing" class="msg-edit">
        <textarea v-model="editText" class="me-ta" rows="3" @keydown.esc.prevent="editing = false" />
        <div class="me-btns">
          <button type="button" class="ma-btn" :disabled="!editText.trim()" @click="saveEdit">保存并重发</button>
          <button type="button" class="ma-btn" @click="editing = false">取消</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { UiIcon } from '../ui'
import MarkdownRenderer from '../MarkdownRenderer.vue'
import BlockHost from '../blocks/BlockHost.vue'
import type { ChatMessage } from '../../composables/useAssistant'

/**
 * 组件属性定义。Component props definition.
 * @property message - 聊天消息对象。Chat message object.
 * @property index - 消息在列表中的下标（分叉/编辑/重生成定位用）。Message index (for fork/edit/regen targeting).
 * @property canAct - 是否允许消息级动作（回合空闲且有会话）。Whether message-level actions are allowed.
 */
const props = withDefaults(
  defineProps<{ message: ChatMessage; index?: number; canAct?: boolean }>(),
  { index: -1, canAct: false },
)

/**
 * 组件事件定义。Component events definition.
 * @event retry - 重试失败的工具调用。Retry a failed tool call.
 * @event cancel - 取消运行中的工具调用。Cancel a running tool call.
 * @event fork - 从该消息处（含）分叉为新会话。Fork at this message (inclusive).
 * @event edit - 编辑用户消息并重发。Edit the user message and resend.
 * @event regen - 重新生成该助手回复。Regenerate this assistant reply.
 */
const emit = defineEmits<{
  retry: [id: string]
  cancel: [id: string]
  fork: [index: number]
  edit: [index: number, text: string]
  regen: [index: number]
}>()

/** 内联编辑态与草稿。Inline edit state and draft. */
const editing = ref(false)
const editText = ref('')

/** 进入编辑：以当前投影文本为草稿。Enter edit: seed the draft from the projection. */
function startEdit() {
  editText.value = props.message.text
  editing.value = true
}

/** 保存并重发（空文本不提交）。Save and resend (empty text is not submitted). */
function saveEdit() {
  const t = editText.value.trim()
  if (!t) return
  editing.value = false
  emit('edit', props.index, t)
}

/**
 * 计算角色显示名称：user→'你', assistant→'衍衡', system→'系统'。
 * Compute role display name: user→'你', assistant→'衍衡', system→'系统'.
 */
const roleName = computed(() => {
  switch (props.message.role) {
    case 'user': return '你'
    case 'assistant': return '衍衡'
    default: return '系统'
  }
})

/**
 * 格式化时间戳为中文格式（HH:MM）。Format timestamp to Chinese format (HH:MM).
 * @param ts - 时间戳毫秒数。Timestamp in milliseconds.
 */
function formatTime(ts: number) {
  const d = new Date(ts)
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}
</script>

<style scoped>
/* 消息项容器及入场动画。Message item container and entrance animation. */
.msg-item { display: flex; gap: 8px; align-items: flex-start; animation: msg-in .32s var(--ease-out) both; }
.msg-item.system { justify-content: center; }
@keyframes msg-in { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

/* 消息头像。Message avatar. */
.msg-avatar {
  width: 26px; height: 26px; border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center; margin-top: 2px;
}
.msg-avatar.assistant { background: var(--brand-grad); color: var(--text-on-brand); }
.msg-avatar.user { background: var(--bg-3); color: var(--text-2); }

/* 消息内容区域。Message body area. */
.msg-body { flex: 1; min-width: 0; display: flex; flex-direction: column; }
/* 消息元信息行。Message meta line. */
.msg-meta { display: flex; align-items: baseline; gap: 6px; padding: 0 4px 2px; }
.msg-role { font-size: 11px; color: var(--text-3); }
.msg-time { font-size: 10px; color: var(--text-3); opacity: .8; }
.msg-item.user .msg-meta { flex-direction: row-reverse; }

/* 消息气泡。Message bubble. */
.msg-bubble {
  position: relative; max-width: 90%;
  padding: 8px 12px; border-radius: var(--r-lg);
  font-size: var(--fs-sm); line-height: 1.5; word-break: break-word;
}
/* 用户气泡：右对齐品牌渐变。User bubble: right-aligned brand gradient. */
.msg-bubble.user {
  align-self: flex-end;
  background: var(--bubble-user); color: var(--bubble-user-text); font-weight: 500;
  border-bottom-right-radius: 4px;
}
.msg-bubble.user::after {
  content: ''; position: absolute; right: -5px; bottom: 6px;
  width: 10px; height: 10px; background: var(--brand-c3);
  border-bottom-right-radius: 3px; transform: rotate(45deg);
}
/* 助手气泡：左对齐暗色 + 品牌左边框。Assistant bubble: left-aligned dark with brand left border. */
.msg-bubble.assistant {
  align-self: flex-start;
  background: var(--bubble-ai); color: var(--text-1);
  border-left: 2px solid var(--bubble-ai-border);
  border-bottom-left-radius: 4px;
}
/* 系统气泡：居中红色警告风格（语义令牌 --bubble-sys-*）。System bubble: centered red warning style (semantic tokens). */
.msg-bubble.system {
  align-self: center; background: var(--bubble-sys); color: var(--bubble-sys-text);
  font-size: 12px; max-width: 80%; text-align: center;
}
.msg-text { white-space: pre-wrap; }

/* 消息级操作条（hover 显示）。Message action bar (shown on hover). */
.msg-actions {
  display: flex; gap: 6px; margin-top: 4px; opacity: 0;
  transition: opacity var(--dur-fast, .15s) var(--ease-out, ease);
}
.msg-item:hover .msg-actions, .msg-actions:focus-within { opacity: 1; }
.msg-item.user .msg-actions { justify-content: flex-end; }
.ma-btn {
  border: 1px solid var(--border-soft); background: var(--bg-1, rgba(15, 23, 42, .5));
  color: var(--text-3); font-size: var(--fs-2xs); border-radius: 999px;
  padding: 2px 9px; cursor: pointer;
}
.ma-btn:hover { color: var(--text-1); border-color: var(--brand-c3, #93c5fd); }
.ma-btn:disabled { opacity: .5; cursor: default; }

/* 内联编辑区。Inline edit area. */
.msg-edit { display: flex; flex-direction: column; gap: 6px; margin-top: 6px; min-width: 240px; }
.msg-item.user .msg-edit { align-items: flex-end; }
.me-ta {
  width: 100%; min-width: 240px; resize: vertical;
  background: var(--bg-1, rgba(15, 23, 42, .6)); color: var(--text-1);
  border: 1px solid var(--border-soft); border-radius: var(--r-md, 8px);
  padding: 6px 8px; font-size: var(--fs-sm); font-family: inherit; line-height: 1.5;
}
.me-btns { display: flex; gap: 6px; }
</style>
