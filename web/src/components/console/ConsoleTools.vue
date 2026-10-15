<template>
  <ConsolePane :max-width="720">
    <!-- 首次加载尚未完成（tools 仍为 null 且无错误）时统一显示加载中，避免闪现空状态。
         Show the loading state until the first load completes (tools still null with no error), avoiding a flash of the empty state. -->
    <UiEmpty v-if="loading || (tools === null && !error)" text="加载中…" />
    <UiErrorNote v-else-if="error" :error="error" />
    <UiEmpty v-else-if="!(tools ?? []).length" icon="wrench" text="后端没有注册工具" hint="启动后端后这里会自动填充" />
    <!-- 工具列表：展示每个工具的名称、描述，点击展开查看参数定义。Tool list: shows name and description of each tool, click to expand and view parameter definitions. -->
    <div v-else class="tool-cards">
      <UiCard v-for="t in (tools ?? [])" :key="t.function.name" class="tool-card" :padded="false">
        <!-- 折叠触发器：`role="button"` + `tabindex` + Enter/Space + `aria-expanded` —— 键盘可达了。
             ⚠️ **必须带 `data-compact`**：不带会命中 app.css 的全局
             `[role="button"]{min-height:44px;min-width:44px}`，把行从 ~24px 撑到 44px —— 那是外观
             变更。`app.css` 注释写明 `data-compact` 的用途是「密集行内的**展开**钮」，正是这里；
             带上之后几何与从前逐像素一致。
             不做成真 `<button>`：行内除文字外还有 chevron，且**同款结构的任务库行里嵌着「删除」
             按钮**（button 里不能再放 button）—— 两处统一走 div + role。
             Disclosure trigger: role="button" + tabindex + Enter/Space + aria-expanded — keyboard
             reachable. ⚠️ `data-compact` is mandatory: without it the global
             `[role="button"]{min-height:44px}` rule grows the row from ~24px to 44px, a visual
             change. app.css documents `data-compact` for exactly this ("expand triggers in dense
             rows"); with it the geometry stays pixel-identical. Not a real `<button>` because the
             row carries a chevron and the sibling task-library row nests a 删除 button (a button
             cannot contain a button) — both use div + role. -->
        <div
          class="tool-head"
          role="button"
          tabindex="0"
          data-compact
          :aria-expanded="open === t.function.name"
          @click="toggle(t.function.name)"
          @keydown.enter.prevent="toggle(t.function.name)"
          @keydown.space.prevent="toggle(t.function.name)"
        >
          <code class="tool-name">{{ t.function.name }}</code>
          <span class="tool-desc">{{ t.function.description }}</span>
          <UiIcon name="chevron-down" :size="12" class="tool-chev" :class="{ rot: open === t.function.name }" />
        </div>
        <div v-if="open === t.function.name" class="tool-params">
          <pre>{{ JSON.stringify(t.function.parameters, null, 2) }}</pre>
        </div>
      </UiCard>
    </div>
  </ConsolePane>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../../api'
import { useAsync } from '../../composables/useAsync'
import { UiCard, UiEmpty, UiErrorNote, UiIcon } from '../ui'
import ConsolePane from './ConsolePane.vue'

/** 当前展开的工具名称（用于折叠/展开切换）。Currently expanded tool name (for collapse/expand toggle). */
const open = ref('')

/** 工具清单加载：统一错误捕获与文案（替代本地 error/loading ref 与 try/catch）。
 *  Tool list loading with unified error capture (replaces the local error/loading refs and try/catch).
 *  后端返回 ok=false 时抛出业务错误，交由 useAsync 统一格式化。 */
const { data: tools, error, loading, run: loadTools } = useAsync(async () => {
  const r = await api.getTools()
  if (!r.ok) throw new Error(r.error || '未知错误')
  return r.tools
})

/**
 * 切换工具详情的展开/折叠。
 * Toggle tool details expand/collapse.
 *
 * @param name 工具名。Tool name.
 */
function toggle(name: string) { open.value = open.value === name ? '' : name }

onMounted(() => { loadTools() })
</script>

<style scoped>
/* `flex-shrink: 0`：ConsolePane 现在是 flex 列，flex 项默认会被压缩 —— 不加这行，工具多到
   超出面板高度时卡片会被**压扁**，而不是让面板滚动。ConsoleEnvView 的 `.env-pre` 同款。
   `flex-shrink: 0`: ConsolePane is a flex column now and flex items shrink by default — without
   this the cards get squashed when there are more tools than fit, instead of the pane scrolling.
   Same reason as ConsoleEnvView's `.env-pre`. */
.tool-cards { display: flex; flex-direction: column; gap: var(--sp-q10); flex-shrink: 0; }
.tool-card { padding: var(--sp-q14) var(--sp-4); }
.tool-head { display: flex; align-items: center; gap: var(--sp-3); cursor: pointer; }
.tool-name { font-family: var(--font-mono); font-size: 13px; color: var(--brand-c2); background: rgba(103, 232, 249, .08); border: 1px solid var(--border-base); border-radius: 6px; padding: var(--sp-q2) var(--sp-2); }
.tool-desc { flex: 1; font-size: var(--fs-xs); color: var(--text-2); }
.tool-chev { color: var(--text-3); transition: transform var(--dur-base); }
.tool-chev.rot { transform: rotate(180deg); }
.tool-params { margin-top: var(--sp-q10); }
/* ⚠️ 站内 5 处 `JSON.stringify(x, null, 2)` **刻意不抽成一个 UiJson 组件**（10.3 提出、视觉批定性）。
   四处呈现的实测差异如下，每一项都不是随机的：

     | 处              | 元素    | 底               | 描边            | 圆角 | 内边距 | 字号      | 字色        | max-height |
     |-----------------|---------|------------------|-----------------|------|--------|-----------|-------------|------------|
     | 此处            | <pre>   | --surface-input  | 1px --border-base | 8px | 10/12 | --fs-2xs | #a5b4fc     | 260        |
     | ConsoleLibrary  | <pre>   | --surface-input  | 1px --border-base | 8px | 8/10  | --fs-2xs | --text-2    | 220        |
     | ToolTimeline    | <code>  | #1e293b          | 无              | 4px  | 4/6    | 继承      | #a5b4fc     | 80         |
     | UnknownBlock    | <pre>   | 无（在 UiHint 内）| 只有 top 1px    | 0    | 8      | --fs-xs   | --text-2    | 无         |

   ToolTimeline 那个必须小一号：它嵌在**已着色**的 `.tt-detail` 面板里，高度只有 80px；
   UnknownBlock 那个**不能有盒子**：它落在 UiHint 的虚线框里，再套一层就是盒中盒。
   合并意味着给组件加 3~4 个 prop（变成配置袋），或强迫四处统一（外观变更）—— 都不划算。

   ⚠️ Five `JSON.stringify(x, null, 2)` sites, **deliberately not merged into a UiJson component**.
   The measured differences are tabulated above and none of them is accidental: ToolTimeline's must
   be a size smaller (it nests inside the already-tinted `.tt-detail` panel, capped at 80px) and
   UnknownBlock's must have no box at all (it already sits inside UiHint's dashed frame). Merging
   would mean 3–4 props (a config bag) or forcing all four to one look (a visual change). */
.tool-params pre { margin: 0; background: var(--surface-input); border: 1px solid var(--border-base); border-radius: 8px; padding: var(--sp-q10) var(--sp-3); font-size: var(--fs-2xs); line-height: 1.6; color: #a5b4fc; overflow-x: auto; max-height: 260px; overflow-y: auto; }
</style>
