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
        <!-- 折叠触发器仍是 div（非 button）：加 role="button" 会命中 app.css 的全局
             `[role="button"]{min-height:44px;min-width:44px}` 最小触达规则，把行撑高
             —— 那是**外观变更**，归视觉批裁定，不在 a11y 批里偷偷做。
             Still a div, not a button: role="button" would match app.css's global
             `[role="button"]{min-height:44px}` touch-target rule and grow the row — a visual
             change, for the visual batch to decide deliberately. -->
        <div class="tool-head" @click="toggle(t.function.name)">
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
.tool-cards { display: flex; flex-direction: column; gap: var(--sp-q10); }
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
