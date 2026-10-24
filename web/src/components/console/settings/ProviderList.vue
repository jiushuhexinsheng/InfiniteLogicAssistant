<template>
  <!-- 供应商列表：空态引导 + 新增入口 + 每行摘要；删除在本组件内先确认。
       Provider list: empty-state hint + add entry + one summary per row; deletion is
       confirmed here before emitting. -->
  <div class="provider-list">
    <div v-if="providers.length" class="pl-rows">
      <ProviderRow
        v-for="p in providers"
        :key="p.id"
        :provider="p"
        @edit="$emit('edit', p.id)"
        @activate="$emit('activate', p.id)"
        @remove="askRemove(p.id)"
      />
    </div>
    <p v-else class="pl-empty">
      还没有供应商。点击「新增供应商」开始；已有自填 profile 也会显示在这里。
    </p>
    <UiButton variant="secondary" size="sm" class="pl-add" @click="$emit('add')">
      新增供应商 / Add Provider
    </UiButton>

    <ConfirmDialog
      v-model="confirmOpen"
      title="删除供应商"
      :message="confirmMessage"
      confirm-text="删除"
      @confirm="confirmRemove"
    />
  </div>
</template>

<script setup lang="ts">
/** 供应商列表 + 删除确认。Provider list with inline delete confirmation. */
import { computed, ref } from 'vue'
import { ConfirmDialog, UiButton } from '../../ui'
import ProviderRow from './ProviderRow.vue'
import type { ProviderSummary } from './providerTypes'

const props = defineProps<{ providers: ProviderSummary[] }>()

const emit = defineEmits<{
  add: []
  edit: [id: string]
  remove: [id: string]
  activate: [id: string]
}>()

/** 待删除的供应商 id。Provider awaiting confirmation. */
const pending = ref('')
const confirmOpen = ref(false)

/** 确认文案。Confirmation copy. */
const confirmMessage = computed(() =>
  `删除供应商「${pending.value}」及其模型与 API Key？此操作不可撤销。`)

/** 打开删除确认。Open the delete confirmation. */
function askRemove(id: string): void {
  pending.value = id
  confirmOpen.value = true
}

/** 确认删除。Confirm deletion. */
function confirmRemove(): void {
  const id = pending.value
  pending.value = ''
  if (id) emit('remove', id)
}
</script>

<style scoped>
.provider-list { display: flex; flex-direction: column; gap: var(--sp-2); }
.pl-rows { display: flex; flex-direction: column; gap: var(--sp-2); }
.pl-empty { margin: 0; font-size: var(--fs-2xs); color: var(--text-3); }
.pl-add { align-self: flex-start; }
</style>
