<template>
  <!-- 语音链路能力卡：编号 + 中英文名 + 模式 + 详情 + 状态点；整卡可点跳转。 -->
  <button type="button" class="voice-tile" :class="tone" :title="reason || detail" @click="$emit('select')">
    <span class="vt-order">{{ order }}</span>
    <span class="vt-body">
      <span class="vt-name">
        <b>{{ zh }}</b>
        <i>{{ en }}</i>
        <span v-if="mode" class="vt-mode">{{ mode }}</span>
      </span>
      <span class="vt-detail">{{ detail }}</span>
    </span>
    <span class="vt-dot" aria-hidden="true"></span>
    <span v-if="arrow" class="vt-arrow" aria-hidden="true">→</span>
  </button>
</template>

<script setup lang="ts">
/** 能力卡（纯展示）。Presentational capability tile. */
withDefaults(defineProps<{
  order: number
  zh: string
  en: string
  detail: string
  tone: 'ok' | 'warn' | 'err' | 'neutral'
  mode?: string
  reason?: string
  arrow?: boolean
}>(), { mode: '', reason: '', arrow: false })

defineEmits<{ select: [] }>()
</script>

<style scoped>
.voice-tile {
  position: relative; display: flex; gap: var(--sp-2); align-items: flex-start;
  padding: var(--sp-2) var(--sp-3); min-width: 0;
  border: 1px solid var(--border-soft); border-radius: var(--r-sm);
  background: rgba(15, 23, 42, .55); color: var(--text-2);
  text-align: left; cursor: pointer;
}
.voice-tile:hover { border-color: var(--border-base); background: rgba(148, 163, 184, .07); }
.vt-order {
  flex-shrink: 0; width: 18px; height: 18px; border-radius: 50%;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: var(--fs-2xs); color: var(--text-3); border: 1px solid var(--border-soft);
}
.vt-body { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 2px; }
.vt-name { display: flex; align-items: baseline; gap: var(--sp-q6); flex-wrap: wrap; }
.vt-name b { font-size: var(--fs-xs); color: var(--text-1); }
.vt-name i { font-size: var(--fs-2xs); color: var(--text-3); font-style: normal; }
.vt-mode {
  font-size: var(--fs-2xs); color: var(--brand-c2);
  border: 1px solid rgba(103, 232, 249, .28); border-radius: var(--r-full);
  padding: 0 var(--sp-q6); line-height: 1.6;
}
.vt-detail { font-size: var(--fs-2xs); color: var(--text-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.vt-dot { width: 7px; height: 7px; border-radius: 50%; margin-top: 6px; background: var(--text-3); flex-shrink: 0; }
.vt-arrow {
  position: absolute; right: -11px; top: 50%; transform: translateY(-50%);
  color: var(--text-3); font-size: var(--fs-2xs); line-height: 1; z-index: 1;
}
.voice-tile.ok .vt-dot { background: #34d399; box-shadow: 0 0 6px rgba(52, 211, 153, .6); }
.voice-tile.warn .vt-dot { background: #fbbf24; }
.voice-tile.err .vt-dot { background: #f87171; box-shadow: 0 0 6px rgba(248, 113, 113, .5); }
</style>
