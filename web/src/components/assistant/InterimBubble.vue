<template>
  <!-- 识别中的临时用户气泡：原地替换中间稿，定稿后由正常消息接替。
       Interim user bubble: the interim is replaced in place; the final message takes over. -->
  <div class="interim-turn">
    <div class="interim-bubble" :class="{ ghost }">
      <span class="interim-badge">{{ ghost ? '未进入对话' : '正在识别' }}</span>
      <span class="interim-text">{{ text }}</span>
      <span v-if="!ghost" class="caret" aria-hidden="true"></span>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 流式识别临时气泡（右侧、虚线、浅色；不进入 messages 数组）。
 * Streaming interim bubble (right side, dashed, faint; never enters the messages array).
 */
defineProps<{
  text: string
  /** 未进入聊天记录的旁白（短暂显示）。Heard-but-discarded text (briefly shown). */
  ghost?: boolean
}>()
</script>

<style scoped>
.interim-turn {
  display: flex;
  justify-content: flex-end;
  animation: interim-in .18s var(--ease-out) both;
}
@keyframes interim-in {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}
.interim-bubble {
  max-width: 85%;
  display: inline-flex;
  align-items: baseline;
  gap: var(--sp-2);
  padding: var(--sp-q10) var(--sp-q14);
  border-radius: 16px;
  border-bottom-right-radius: 4px;
  border: 1px dashed color-mix(in srgb, var(--brand-c2) 45%, transparent);
  background: color-mix(in srgb, var(--brand-c2) 8%, transparent);
  color: var(--text-1);
  font-size: var(--fs-sm);
  line-height: 1.6;
  word-break: break-word;
  white-space: pre-wrap;
}
.interim-bubble.ghost {
  border-style: dotted;
  border-color: var(--border-base);
  background: transparent;
  color: var(--text-3);
}
.interim-badge {
  flex: 0 0 auto;
  font-size: var(--fs-2xs);
  color: var(--brand-c2);
  border: 1px solid color-mix(in srgb, var(--brand-c2) 30%, transparent);
  border-radius: var(--r-full);
  padding: 0 var(--sp-q6);
  line-height: 1.5;
}
.interim-bubble.ghost .interim-badge { color: var(--text-3); border-color: var(--border-base); }
.interim-text { min-width: 0; }
.caret {
  display: inline-block;
  width: 2px;
  height: 1em;
  margin-left: 2px;
  vertical-align: -2px;
  background: var(--brand-c2);
  animation: caret-blink 1s steps(2, start) infinite;
}
@keyframes caret-blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
</style>
