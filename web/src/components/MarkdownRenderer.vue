<template>
  <!-- 渲染结果经 v-html 插入，内容已按 token 安全转义 + href 白名单。Rendered output inserted via v-html; content is token-escaped and href whitelisted. -->
  <div class="md" v-html="html"></div>
</template>

<script setup lang="ts">
/**
 * 轻量 Markdown 渲染器，支持代码块、粗体、斜体、链接、列表等基本语法。
 * Lightweight Markdown renderer supporting code blocks, bold, italic, links, lists and other basic syntax.
 */
import { computed } from 'vue'

/** 属性：待渲染的原始 Markdown 文本。Props: raw Markdown text to render. */
const props = defineProps<{ text: string }>()

/**
 * 对字符串进行 HTML 实体转义，防止 XSS 注入。
 * Escape HTML entities in a string to prevent XSS injection.
 */
function esc(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/**
 * 验证 URL 协议安全性，拦截 javascript:/data: 等危险协议。
 * Validate URL protocol safety, block dangerous protocols like javascript:/data:.
 */
function safeHref(url: string): string {
  // 仅放行 http(s)/mailto/相对路径；拦截 javascript:/data: 等危险协议。Only allow http(s)/mailto/relative paths; block javascript:/data: and other dangerous protocols.
  if (/^(javascript|data|vbscript):/i.test(url)) return '#'
  return url
}

/** 将 Markdown 文本解析为安全的 HTML 字符串。Parse Markdown text into a safe HTML string. */
const html = computed(() => {
  let s = esc(props.text ?? '')
  // 代码块 ``` ... ```。Code block ``` ... ```
  s = s.replace(/```([\s\S]*?)```/g, (_, code) => '<pre><code>' + code + '</code></pre>')
  // 行内代码 `x`。Inline code `x`
  s = s.replace(/`([^`\n]+)`/g, (_, code) => '<code>' + code + '</code>')
  // 粗体 **x** 与斜体 *x*。Bold **x** and italic *x*
  s = s.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
  s = s.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
  // 链接 [t](url)。Link [t](url)
  s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, title, url) =>
    `<a href="${safeHref(url)}" target="_blank" rel="noopener">${title}</a>`)
  // 无序列表 - item。Unordered list - item
  s = s.replace(/(^|\n)[ \t]*[-*][ \t]+([^\n]+)/g, '$1<li>$2</li>')
  // 有序列表 1. item。Ordered list 1. item
  s = s.replace(/(^|\n)[ \t]*\d+[.、][ \t]+([^\n]+)/g, '$1<li>$2</li>')
  s = s.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul>$1</ul>')
  // 段落与换行：聊天场景下把换行折叠为空格（而非 <br/>）。按句换行的回复若拆成多行，
  // 会让 .msg-bubble（fit-content 收缩）塌成每行两三个字的窄气泡。
  // Paragraphs and line breaks: in chat mode, collapse newlines to spaces (not <br/>).
  // Multi-line replies would cause .msg-bubble (fit-content shrink) to collapse into narrow bubbles with only a few characters per line.
  s = s.replace(/\s*\n\s*/g, ' ')
  return '<p>' + s + '</p>'
})
</script>

<style scoped>
.md { line-height: 1.65; word-break: break-word; font-size: var(--fs-sm); }
.md :deep(p) { margin: 0 0 8px; }
.md :deep(p:last-child) { margin-bottom: 0; }
.md :deep(code) { background: rgba(148, 163, 184, .16); padding: 1px 5px; border-radius: 5px; font-size: .88em; font-family: var(--font-mono); }
.md :deep(pre) { background: rgba(2, 6, 23, .7); padding: 10px 12px; border-radius: var(--r-md); overflow-x: auto; margin: 8px 0; border: 1px solid var(--border-soft); }
.md :deep(pre code) { background: none; padding: 0; }
.md :deep(a) { color: var(--brand-c2); text-decoration: underline; text-underline-offset: 2px; }
.md :deep(ul) { padding-left: 20px; margin: 4px 0 8px; display: grid; gap: 4px; }
.md :deep(strong) { color: var(--text-1); font-weight: 600; }
.md :deep(em) { color: var(--text-2); }
</style>
