<template>
  <!-- 通用确认框：标题 + 正文 + 取消/确认；确认动作由调用方决定（默认危险色）。
       Generic confirm dialog: title + message + cancel/confirm; the action is the
       caller's, styled as dangerous by default. -->
  <UiModal :model-value="modelValue" :title="title" @update:model-value="close">
    <p class="ui-confirm-msg">{{ message }}</p>
    <div class="ui-confirm-actions">
      <UiButton variant="secondary" size="sm" @click="cancel">{{ cancelText }}</UiButton>
      <UiButton :variant="danger ? 'danger' : 'primary'" size="sm" @click="confirm">
        {{ confirmText }}
      </UiButton>
    </div>
  </UiModal>
</template>

<script setup lang="ts">
/** 确认框：v-model 控制开合，confirm/cancel 各自抛事件并关闭。 */
import UiButton from './UiButton.vue'
import UiModal from './UiModal.vue'

const props = withDefaults(defineProps<{
  modelValue: boolean
  title: string
  message: string
  confirmText?: string
  cancelText?: string
  danger?: boolean
}>(), { confirmText: '确认', cancelText: '取消', danger: true })

const emit = defineEmits<{
  'update:modelValue': [v: boolean]
  confirm: []
  cancel: []
}>()

/** 关闭（不改语义）。Close without a verdict. */
function close(value: boolean): void {
  emit('update:modelValue', value)
}

/** 取消：关闭并抛 cancel。Cancel: close and emit. */
function cancel(): void {
  emit('update:modelValue', false)
  emit('cancel')
}

/** 确认：关闭并抛 confirm。Confirm: close and emit. */
function confirm(): void {
  emit('update:modelValue', false)
  emit('confirm')
}
</script>

<style scoped>
.ui-confirm-msg { margin: 0 0 var(--sp-3); color: var(--text-2); font-size: var(--fs-sm); line-height: 1.7; }
.ui-confirm-actions { display: flex; justify-content: flex-end; gap: var(--sp-2); }
</style>
