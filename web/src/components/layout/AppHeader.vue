<template>
  <header class="app-header">
    <button class="ah-brand" type="button" @click="router.push('/')" aria-label="返回首页">
      <span class="ah-mark">∞</span>
      <span class="ah-name">无限逻辑</span>
    </button>
    <nav class="ah-nav" aria-label="主导航">
      <button
        class="ah-nav-item"
        :class="{ active: route.path === '/' }"
        type="button"
        @click="router.push('/')"
        :aria-current="route.path === '/' ? 'page' : undefined"
      >开始页</button>
      <button
        class="ah-nav-item"
        :class="{ active: route.path === '/console' }"
        type="button"
        @click="router.push('/console')"
        :aria-current="route.path === '/console' ? 'page' : undefined"
      >控制台</button>
    </nav>
    <div class="ah-mode" role="radiogroup" aria-label="助手模式">
      <button
        class="ah-mode-item"
        :class="{ on: assistantMode === 'chat' }"
        type="button"
        @click="setAssistantMode('chat')"
        role="radio"
        :aria-checked="assistantMode === 'chat'"
      >对话</button>
      <button
        class="ah-mode-item"
        :class="{ on: assistantMode === 'task' }"
        type="button"
        @click="setAssistantMode('task')"
        role="radio"
        :aria-checked="assistantMode === 'task'"
      >任务</button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { assistantMode, setAssistantMode } from '../../composables/assistant/store'

const router = useRouter()
const route = useRoute()
</script>

<style scoped>
.app-header {
  width: 100%; height: 56px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 var(--sp-6);
  background: var(--bg-1);
  border-bottom: 1px solid var(--border-base);
}
.ah-brand {
  display: flex; align-items: center; gap: var(--sp-2);
  background: none; border: none; cursor: pointer; padding: var(--sp-2);
}
.ah-mark {
  width: 32px; height: 32px; border-radius: var(--r-md);
  background: var(--brand-grad); color: #ffffff;
  display: grid; place-items: center; font-size: var(--fs-lg); font-weight: 700;
}
.ah-name { font-size: var(--fs-lg); font-weight: 600; color: var(--text-1); }
.ah-nav {
  display: flex; gap: var(--sp-1); padding: var(--sp-1);
  border-radius: var(--r-full); background: var(--bg-2);
  border: 1px solid var(--border-base);
}
.ah-nav-item {
  border: none; cursor: pointer; font-family: inherit;
  font-size: var(--fs-sm);
  padding: var(--sp-2) var(--sp-4); border-radius: var(--r-full);
  background: transparent; color: var(--text-2);
  min-height: var(--min-target-size);
}
.ah-nav-item:hover {
  background: var(--surface-control-hover);
  color: var(--text-1);
}
.ah-nav-item.active {
  background: var(--brand-c2);
  color: var(--text-on-brand);
  font-weight: 600;
}
.ah-mode {
  margin-left: auto;
  display: flex; gap: var(--sp-1);
  background: var(--bg-2);
  border-radius: var(--r-full);
  padding: var(--sp-1);
  border: 1px solid var(--border-base);
}
.ah-mode-item {
  font-size: var(--fs-xs);
  color: var(--text-3);
  background: none;
  border: none;
  border-radius: var(--r-full);
  padding: var(--sp-2) var(--sp-3);
  cursor: pointer;
  min-height: var(--min-target-size);
}
.ah-mode-item:hover { color: var(--text-2); }
.ah-mode-item.on {
  color: var(--text-on-brand);
  background: var(--brand-c2);
}
</style>
