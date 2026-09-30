<template>
  <!-- RAG 来源模块（docs/designs/05 §3.2）：编号 chips + 折叠。
       默认折叠（后端 meta.collapsed），点击展开看 path/section/分数。
       RAG sources block (docs/designs/05 §3.2): numbered chips + collapse.
       Collapsed by default (backend meta.collapsed); click to reveal path/section/score. -->
  <div class="blk-sources">
    <button type="button" class="bs-head" @click="open = !open">
      <span class="bs-title">📄 来源 {{ items.length }} 个</span>
      <span class="bs-caret">{{ open ? '▾' : '▸' }}</span>
    </button>
    <ul v-if="open" class="bs-list">
      <li v-for="it in items" :key="it.n" class="bs-item" :title="it.path">
        <span class="bs-n">[{{ it.n }}]</span>
        <span class="bs-label">{{ it.section || basename(it.path) }}</span>
        <span class="bs-path">{{ it.path }}</span>
        <span v-if="it.score != null" class="bs-score">{{ Number(it.score).toFixed(2) }}</span>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Block, Skin } from '../../blocks/types'

/**
 * 组件属性定义。Component props definition.
 * @property block - 来源块（payload.items = [{n, path, section, score}]）。Sources block.
 * @property skin - 渲染皮肤。Render skin.
 */
const props = defineProps<{ block: Block; skin?: Skin }>()

/** 来源条目。A source entry. */
interface SrcItem { n: number; path: string; section: string; score?: number }

/** 条目列表（容错：非数组给空）。Item list (tolerant: non-array → empty). */
const items = computed<SrcItem[]>(() => {
  const v = props.block.payload?.items
  return Array.isArray(v) ? v : []
})

/** 展开态（初始取块 meta.collapsed，后端默认折叠）。Expanded state (initial from
 *  meta.collapsed; collapsed by default on the backend). */
const ref0 = props.block.meta?.collapsed
const open = ref(ref0 === false)

/** 取路径末段（label 缺省用）。Basename of the path (label fallback). */
function basename(p: string): string {
  const seg = String(p || '').split(/[\\/]/)
  return seg[seg.length - 1] || p
}
</script>

<style scoped>
.blk-sources {
  border: 1px solid var(--border-soft, rgba(148, 163, 184, .18));
  border-radius: var(--r-md, 8px);
  background: var(--bg-1, rgba(15, 23, 42, .4));
  font-size: var(--fs-2xs, 11px);
  overflow: hidden;
}
.bs-head {
  width: 100%; display: flex; align-items: center; justify-content: space-between;
  gap: 8px; padding: 5px 10px; background: none; border: 0; cursor: pointer;
  color: var(--text-3); font-size: inherit;
}
.bs-head:hover { color: var(--text-2); }
.bs-caret { opacity: .7; }
.bs-list { list-style: none; margin: 0; padding: 2px 8px 7px; display: flex; flex-direction: column; gap: 3px; }
.bs-item {
  display: flex; align-items: baseline; gap: 6px; min-width: 0;
  color: var(--text-2);
}
.bs-n { color: var(--brand-c3, #93c5fd); font-weight: 600; flex: none; }
.bs-label { flex: none; max-width: 40%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bs-path { flex: 1; min-width: 0; color: var(--text-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; direction: rtl; text-align: left; }
.bs-score { flex: none; color: var(--text-3); font-variant-numeric: tabular-nums; }
</style>
