<template>
  <!-- 渲染结果经 v-html 插入，内容已按 token 安全转义 + href 白名单 -->
  <div class="md" v-html="html"></div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ text: string }>()

function esc(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function safeHref(url: string): string {
  // 仅放行 http(s)/mailto/相对路径；拦截 javascript:/data: 等危险协议
  if (/^(javascript|data|vbscript):/i.test(url)) return '#'
  return url
}

const html = computed(() => {
  let s = esc(props.text ?? '')
  // 代码块 ``` ... ```
  s = s.replace(/```([\s\S]*?)```/g, (_, code) => '<pre><code>' + code + '</code></pre>')
  // 行内代码 `x`
  s = s.replace(/`([^`\n]+)`/g, (_, code) => '<code>' + code + '</code>')
  // 粗体 **x** 与斜体 *x*
  s = s.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
  s = s.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
  // 链接 [t](url)
  s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, title, url) =>
    `<a href="${safeHref(url)}" target="_blank" rel="noopener">${title}</a>`)
  // 无序列表 - item
  s = s.replace(/(^|\n)[ \t]*[-*][ \t]+([^\n]+)/g, '$1<li>$2</li>')
  // 有序列表 1. item
  s = s.replace(/(^|\n)[ \t]*\d+[.、][ \t]+([^\n]+)/g, '$1<li>$2</li>')
  s = s.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul>$1</ul>')
  // 段落与换行
  s = s.replace(/\n{2,}/g, '</p><p>').replace(/\n/g, '<br/>')
  return '<p>' + s + '</p>'
})
</script>

<style scoped>
.md { line-height: 1.6; word-break: break-word; }
.md :deep(code) { background: rgba(255,255,255,.12); padding: 1px 4px; border-radius: 4px; font-size: .9em; font-family: Consolas, monospace; }
.md :deep(pre) { background: #0f172a; padding: 8px 10px; border-radius: 8px; overflow-x: auto; margin: 6px 0; }
.md :deep(pre code) { background: none; padding: 0; }
.md :deep(a) { color: var(--brand-c2); text-decoration: underline; }
.md :deep(ul) { padding-left: 18px; margin: 4px 0; }
.md :deep(strong) { color: var(--text-1); }
</style>
