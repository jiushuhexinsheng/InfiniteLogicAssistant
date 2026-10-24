<template>
  <!-- 供应商行：名称/协议/模型数/地址/Key 状态 + 操作区（设为当前/编辑/删除）。
       Provider row: name/protocol/model count/endpoint/key status plus actions.
       整行点击 = 编辑；操作区 click.stop，避免误触。 -->
  <div class="pr-row" :class="{ on: provider.active }" @click="$emit('edit')">
    <div class="pr-main">
      <div class="pr-title">
        <span class="pr-name">{{ provider.name || provider.id }}</span>
        <UiChip v-if="provider.active" tone="ok" :dot="false">当前</UiChip>
        <span class="pr-meta">{{ provider.protocol || 'openai' }} · {{ provider.modelCount }} 模型</span>
      </div>
      <span class="pr-url">{{ provider.endpoint || '未填 Endpoint' }}</span>
    </div>
    <UiChip :tone="provider.keySet ? 'ok' : 'warn'" :dot="false">
      {{ provider.keySet ? 'Key 已设置' : 'Key 未设置' }}
    </UiChip>
    <div class="pr-actions" @click.stop>
      <UiButton
        v-if="!provider.active"
        variant="ghost" size="sm" class="pr-activate"
        @click="$emit('activate')"
      >设为当前</UiButton>
      <UiButton variant="secondary" size="sm" class="pr-edit" @click="$emit('edit')">编辑</UiButton>
      <UiButton variant="secondary" size="sm" hover="danger" class="pr-del" @click="$emit('remove')">
        删除
      </UiButton>
    </div>
  </div>
</template>

<script setup lang="ts">
/** 单条供应商摘要（由页面按 models ∪ model 计算 modelCount）。One provider summary. */
import { UiButton, UiChip } from '../../ui'
import type { ProviderSummary } from './providerTypes'

defineProps<{ provider: ProviderSummary }>()

defineEmits<{ edit: []; remove: []; activate: [] }>()
</script>

<style scoped>
.pr-row {
  display: flex; align-items: center; gap: var(--sp-3); padding: var(--sp-2) var(--sp-3);
  border: 1px solid var(--border-soft); border-radius: var(--r-sm);
  background: rgba(15, 23, 42, .5); cursor: pointer;
}
.pr-row:hover, .pr-row.on { border-color: var(--brand-c2); background: rgba(103, 232, 249, .06); }
.pr-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.pr-title { display: flex; align-items: baseline; gap: var(--sp-2); flex-wrap: wrap; }
.pr-name { font-size: var(--fs-sm); font-weight: 600; color: var(--text-1); }
.pr-meta { font-size: var(--fs-2xs); color: var(--text-3); }
.pr-url {
  font-size: var(--fs-2xs); color: var(--text-3); font-family: var(--font-mono);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.pr-actions { display: flex; align-items: center; gap: var(--sp-1); flex-shrink: 0; }
</style>
