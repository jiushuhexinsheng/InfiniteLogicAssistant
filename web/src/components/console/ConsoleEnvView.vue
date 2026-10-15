<template>
  <ConsolePane :max-width="860">
    <!-- 环境快照头部：刷新按钮和加载状态。Environment snapshot header: refresh button and loading state. -->
    <div class="env-head">
      <UiButton variant="ghost" size="sm" @click="loadEnv">刷新</UiButton>
      <span v-if="loading" class="env-loading">加载中…</span>
    </div>
    <UiErrorNote v-if="error" :error="error" />
    <!-- 环境快照内容区域：有内容时显示 <pre>，否则显示空提示。Environment snapshot content: shows <pre> when content exists, otherwise an empty hint. -->
    <pre v-else-if="content" class="env-pre">{{ content }}</pre>
    <UiEmpty v-else-if="!loading" icon="globe" text="暂无环境快照" hint="首次运行会自动生成" />
  </ConsolePane>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { api } from '../../api'
import { useAsync } from '../../composables/useAsync'
import { UiButton, UiEmpty, UiErrorNote } from '../ui'
import ConsolePane from './ConsolePane.vue'

/** 环境快照加载：统一错误捕获与文案（替代原先把 '加载失败: ' 拼进 content 再渲染到 <pre> 的写法）。
 *  Environment snapshot loading with unified error capture (replaces baking '加载失败: ' into content and rendering it inside <pre>). */
const { data: content, error, loading, run: loadEnv } = useAsync(async () => {
  const r = await api.getEnv()
  return r.content
})

onMounted(() => { loadEnv() })
</script>

<style scoped>
.env-head { display: flex; align-items: center; gap: var(--sp-q10); margin-bottom: var(--sp-q10); }
.env-loading { font-size: var(--fs-xs); color: var(--text-3); }
/* `flex-shrink: 0`：ConsolePane 现在是 flex 列。不加这行，这段带 `max-height: 60vh` 的
   `<pre>` 会被当作可压缩的 flex 项 —— 这正是 ConsolePane 旧注释里那条警告（「flex 化会压扁
   .env-pre」）的真正病根。声明不可压缩后，外观与块级流时逐像素相同。
   `flex-shrink: 0`: ConsolePane is a flex column now. Without this, this max-height'd `<pre>`
   would be treated as a squishable flex item — the real cause behind ConsolePane's old warning.
   Declaring it unshrinkable keeps the look pixel-identical to the block-flow days. */
.env-pre { background: var(--surface-input); border: 1px solid var(--border-base); border-radius: 10px; padding: var(--sp-q14) var(--sp-4); font-size: var(--fs-xs); line-height: 1.7; color: var(--text-1); overflow: auto; max-height: 60vh; white-space: pre-wrap; word-break: break-all; flex-shrink: 0; }
</style>
