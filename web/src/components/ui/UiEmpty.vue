<template>
  <div class="ui-empty" :class="{ fill }">
    <!-- 图标徽章：给空态一个「入口级」的视觉锚点。图标名与侧栏该页签**同名**（wrench / globe /
         database / history / library / calendar-clock），所以空态读起来像「这一页」，而不是一段
         漂浮在大片深色里的灰字。
         Icon badge: an entry-level anchor for the empty state. The name matches the sidebar icon for
         that very tab, so the empty state reads as "this page" rather than a grey line floating in a
         large dark area. -->
    <div v-if="icon" class="ui-empty-badge"><UiIcon :name="icon" :size="20" /></div>
    <div class="ui-empty-text"><slot>{{ text }}</slot></div>
    <div v-if="hint" class="ui-empty-hint">{{ hint }}</div>
  </div>
</template>

<!-- 空态 / 加载占位。Empty-state / loading placeholder.
     收编原先散在 6 个 console 视图里逐字重复的 `.console-empty`。
     Collects the `.console-empty` blocks that were duplicated verbatim across 6 console views.

     科技感批（10.6）：从「一行灰字」升级为「图标徽章 + 主文案 + 次级说明」。原先几处把说明塞在
     主文案的括号里（`暂无记忆（任务完成后会自动提取）`），与主句同色同号，读起来是一整句长话；
     拆成 hint 后主句先被看到，说明退到第二层。
     Visual batch (10.6): from "one grey line" to "icon badge + primary line + secondary hint". Some
     call sites used to bury the explanation in parentheses at the same size and colour as the main
     sentence; splitting it into `hint` lets the main line land first and pushes the detail down a
     tier. -->
<script setup lang="ts">
import UiIcon from './UiIcon.vue'

/** 空态 Props：主文案 / 图标名（留空则只渲染文案）/ 次级说明。
 *  Empty-state props: primary text, icon name (omit for a text-only state), secondary hint. */
withDefaults(defineProps<{
  /** 主文案（复杂节点走默认 slot）。Primary text (use the default slot for richer nodes). */
  text?: string
  /** 图标名 —— 建议用侧栏该页签的图标。Icon name; use the sidebar tab's icon. */
  icon?: string
  /** 次级说明（`--fs-xs`、更暗），可选。Secondary hint at --fs-xs in a dimmer tone; optional. */
  hint?: string
  /** 长满父容器并在其中**居中**（父容器需是 flex 列，如对话区的 `.console-messages`）。
   *  不传时是「上对齐 + 40px 内边距」，用于列表页签（工具栏下方的空态）。
   *  Grow to fill the parent and centre inside it (the parent must be a flex column, like the
   *  conversation pane's `.console-messages`). Without it the state is top-aligned with 40px
   *  padding, which is what the list tabs want (their empty state sits under a toolbar). */
  fill?: boolean
}>(), { text: '', icon: '', hint: '', fill: false })
</script>

<style scoped>
/* 纵向内边距 40px（10.5 统一值）：原先是 md=40 / sm=30 两档，30px 只有 ConsoleHistory 一个消费者。
   Vertical padding 40px (unified in 10.5): was md=40 / sm=30 with ConsoleHistory the lone 30px user.

   `text-align: center` 对单行文案是 no-op（flex 项宽度=文本宽度），只在长文案换行时生效 ——
   ConsoleLibrary 的说明句会换行，靠它居中。 `text-align: center` is a no-op for a single-line label
   and only matters once the text wraps, which ConsoleLibrary's hint does. */
.ui-empty {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  text-align: center;
  color: var(--text-3); font-size: 13px;
  padding: var(--sp-q40) 0;
}
/* 徽章底/描边都复用既有令牌（品牌色的 .1 淡底 + 玻璃描边）。外发光没有令牌，量级**照抄
   UiChip 的 t-* 族**（`0 0 7px -2px`）—— 那是这套截图门禁里被证明稳的量级，别加大。
   Badge fill and border reuse existing tokens; the bloom has no token and copies UiChip's t-* family
   (`0 0 7px -2px`) — the magnitude proven stable in this screenshot gate. Don't grow it. */
.ui-empty-badge {
  display: flex; align-items: center; justify-content: center;
  width: 44px; height: 44px; margin-bottom: var(--sp-3);
  border-radius: var(--r-full);
  color: var(--brand-c2);
  background: var(--surface-control-hover);
  border: 1px solid var(--glass-border);
  box-shadow: 0 0 7px -2px rgba(103, 232, 249, .45);
}
/* 主文案比原来的 --text-3 亮一档：徽章一上来，它就从「唯一的字」变成「标题行」。
   The primary line is a step brighter than the old --text-3: with a badge above it, it turns from
   "the only text" into a heading. */
.ui-empty-text { color: var(--text-2); }
.ui-empty-hint { margin-top: var(--sp-1); color: var(--text-3); font-size: var(--fs-xs); line-height: 1.5; }
/* `fill`：长满父容器。基类已经有 `justify-content: center`，高度一被撑起来它才真的生效 ——
   这正是「上对齐」与「居中」两种空态的唯一差别。
   `fill`: grow into the parent. The base rule already carries `justify-content: center`, which only
   bites once the height is stretched — that is the whole difference between the two presentations. */
.ui-empty.fill { flex: 1; }
</style>
