<template>
  <!-- 能力状态行 + 引擎自检：模型是否就位、自检耗时/结果（存在性之外的第二道确认）。
       Capability status rows + engine self-tests: whether models are present and what a
       real load/run reports (a second confirmation beyond mere presence). -->
  <div v-if="showChips && rows.length" class="cs-status">
    <span v-for="row in rows" :key="row.kind" class="cs-status-chip" :class="row.tone">
      {{ row.text }}
    </span>
  </div>

  <div v-if="kinds.length" class="cs-tests">
    <UiButton
      v-for="k in kinds" :key="k" variant="secondary" size="sm"
      :disabled="testing === k" @click="selfTest(k)"
    >
      <BiLabel
        :zh="testing === k ? `自检本地 ${k.toUpperCase()}…` : `自检本地 ${k.toUpperCase()}`"
        :en="testing === k ? `Self-testing ${k.toUpperCase()}…` : `Self-test ${k.toUpperCase()}`"
      />
    </UiButton>
    <template v-for="k in kinds" :key="`r-${k}`">
      <span v-if="engineTests[k]" class="cs-test-result" :class="{ err: !engineTests[k].ok }">
        {{ k.toUpperCase() }}:
        {{ engineTests[k].ok ? (engineTests[k].detail || 'OK') : (engineTests[k].error || '失败') }}
        <em v-if="engineTests[k].latency_ms != null"> · {{ engineTests[k].latency_ms }}ms</em>
      </span>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * 本地模型状态条与引擎自检（从 LocalModelsCard 拆出）。
 * Local-model status chips and engine self-tests (extracted from LocalModelsCard).
 */
import { computed } from 'vue'

import { UiButton } from '../../ui'
import BiLabel from './BiLabel.vue'
import { useLocalModels, type LocalModelsScope, type ModelKind } from './useLocalModels'

const props = defineProps<{ scope: LocalModelsScope }>()

const { engineTests, testing, statusRowsFor, testKindsFor, testEngine } = useLocalModels()

/** 状态条只在识别段落展示（合成/硬件页不重复四能力）。Chips show on the recognition section only. */
const showChips = computed(() => props.scope === 'all' || props.scope === 'recognition')
const rows = computed(() => statusRowsFor(props.scope))
const kinds = computed(() => testKindsFor(props.scope))

/** 自检入口：模板里拿到的 kind 是 string，收敛成 ModelKind。Self-test entry (narrows the kind). */
function selfTest(kind: string) {
  void testEngine(kind as ModelKind)
}
</script>

<style scoped>
.cs-status { display: flex; flex-wrap: wrap; gap: var(--sp-2); margin: var(--sp-2) 0; }
.cs-status-chip {
  font-size: var(--fs-2xs); line-height: 1.6;
  padding: var(--sp-q6) var(--sp-q10); border-radius: var(--r-full);
  border: 1px solid var(--border-base); color: var(--text-2);
  background: rgba(148, 163, 184, .06);
}
.cs-status-chip.ok { color: #34d399; border-color: rgba(52, 211, 153, .35); background: rgba(52, 211, 153, .08); }
.cs-status-chip.err { color: #f87171; border-color: rgba(248, 113, 113, .4); background: rgba(248, 113, 113, .08); }
.cs-status-chip.info { color: var(--brand-c2); border-color: rgba(103, 232, 249, .3); background: rgba(103, 232, 249, .07); }
.cs-tests { display: flex; align-items: center; flex-wrap: wrap; gap: var(--sp-2); margin: var(--sp-2) 0; }
.cs-test-result { font-size: var(--fs-2xs); color: #34d399; }
.cs-test-result.err { color: #f87171; }
.cs-test-result em { font-style: normal; color: var(--text-3); }
</style>
