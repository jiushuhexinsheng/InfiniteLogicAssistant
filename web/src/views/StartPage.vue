<template>
  <div class="page">
    <main class="hero">
      <OrbHero />

      <!-- 状态卡片 -->
      <div class="cards">
        <ServiceStatusCard />

        <StartCard title="语音设置">
          <TtsMini />
        </StartCard>
      </div>

      <FeatureGrid />
      <PageFooter />
    </main>
  </div>
</template>

<!-- 起始页：只负责版面骨架（页 / 主区 / 卡片行），各块交给 components/start/ 下的组件。
     Start page: owns only the layout skeleton (page / hero / card row); each block lives in
     components/start/.

     原先是一份 349 行的单体文件，光球、两张卡、特性网格、页脚与各自的样式全挤在一起 ——
     其中「实时状态」卡的 service-grid 与 ConsoleStatus.vue 高度重复。
     Was a 349-line monolith holding the orb, both cards, the feature grid, the footer and all
     their styles — with the status card's service-grid closely duplicating ConsoleStatus.vue. -->
<script setup lang="ts">
import { onMounted } from 'vue'
import { useConfig } from '../composables/useApi'
import OrbHero from '../components/start/OrbHero.vue'
import ServiceStatusCard from '../components/start/ServiceStatusCard.vue'
import StartCard from '../components/start/StartCard.vue'
import FeatureGrid from '../components/start/FeatureGrid.vue'
import PageFooter from '../components/start/PageFooter.vue'
import TtsMini from '../components/assistant/TtsMini.vue'

/** 全局配置缓存；首屏拉一次，卡片与副标题都读它。Global config cache, fetched once on first paint. */
const app = useConfig()

onMounted(async () => {
  if (!app.config.value) await app.initConfig()
})
</script>

<style scoped>
.page {
  min-height: 100%;
  display: flex;
  flex-direction: column;
}

.hero {
  flex: 1;
  width: 100%;
  max-width: 960px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--sp-6);
  padding: var(--sp-8) var(--sp-5);
}

/* ── 卡片行 ── */
.cards {
  display: flex;
  gap: var(--sp-4);
  flex-wrap: wrap;
  justify-content: center;
  width: 100%;
}
</style>
