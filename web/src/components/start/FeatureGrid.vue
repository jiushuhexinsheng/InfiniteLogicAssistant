<template>
  <section class="features" aria-label="功能特性">
    <div v-for="f in features" :key="f.title" class="feature-item">
      <span class="feature-icon">{{ f.icon }}</span>
      <div class="feature-content">
        <h2 class="feature-title">{{ f.title }}</h2>
        <p class="feature-desc">{{ f.desc }}</p>
      </div>
    </div>
  </section>
</template>

<!-- 起始页功能特性网格。Start-page feature grid. -->
<script setup lang="ts">
/** 特性条目（静态文案）。Feature entries (static copy). */
const features = [
  { icon: '✨', title: '灵感对话', desc: '自然语言直达任务，不必记指令' },
  { icon: '🎤', title: '语音控制', desc: '一句话完成查询、调度与操作' },
  { icon: '💾', title: '记忆常驻', desc: '上下文与偏好长期留存' },
  { icon: '🔧', title: '工具调用', desc: '挂载 MCP 与系统能力' },
]
</script>

<style scoped>
.features {
  width: 100%;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--sp-3);
}

.feature-item {
  display: flex;
  gap: var(--sp-3);
  padding: var(--sp-4);
  background: var(--bg-1);
  border: 1px solid var(--border-base);
  border-radius: var(--r-lg);
}

.feature-icon {
  font-size: var(--fs-xl);
  flex-shrink: 0;
}

.feature-content {
  min-width: 0;
}

.feature-title {
  font-size: var(--fs-md);
  font-weight: 600;
  color: var(--text-1);
  margin-bottom: var(--sp-1);
  margin-top: 0;
}

.feature-desc {
  font-size: var(--fs-xs);
  color: var(--text-3);
  line-height: 1.5;
}
</style>
