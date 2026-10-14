<template>
  <!-- 起始页卡片：薄适配层 —— 外壳本身是 `ui/UiCard`，「卡片长什么样」只剩一份实现。
       原先这里是**第二套卡片外壳**（自己写 bg/border/radius/模糊/发光线 + `.card-header`），
       与 UiCard 并存；Batch 5 判定「两套语言有意共存」在当时成立，但控制台卡片统一到玻璃
       语言之后就成了纯粹的重复。现在只保留**布局**（flex 宽度、圆角裁剪）与两个插槽的接线。

       Start-page card: a thin adapter — the shell itself is `ui/UiCard`, so "what a card looks
       like" has one implementation. This used to be a second card shell (its own background /
       border / radius / blur / hairline plus `.card-header`) coexisting with UiCard. Now only the
       layout and the two slot wirings remain. -->
  <UiCard class="card" :padded="false">
    <template #header>
      <span class="card-title"><slot name="title">{{ title }}</slot></span>
      <slot name="badge" />
    </template>
    <div class="card-body"><slot /></div>
  </UiCard>
</template>

<script setup lang="ts">
import UiCard from '../ui/UiCard.vue'

/** 卡头标题。Title for the card head. */
withDefaults(defineProps<{ title?: string }>(), { title: '' })
</script>

<style scoped>
/* 只剩布局：卡片本体的底/描边/圆角/模糊/发光线全部由 UiCard 提供。
   这些选择器能命中子组件根元素（Vue 把父组件的 scope 属性加到子组件根上）。
   Layout only: the fill / border / radius / blur / hairline all come from UiCard. These
   selectors reach the child component's root (Vue applies the parent's scope attribute to it). */
.card {
  flex: 1 1 400px;
  max-width: 480px;
  overflow: hidden; /* 让标题行的下边框跟着圆角裁剪。Lets the header's bottom border follow the radius. */
}
.card-title {
  font-size: var(--fs-md);
  font-weight: 600;
  color: var(--text-1);
}
.card-body { padding: var(--sp-4); }
/* 网格与刷新按钮的间距（按钮已是 UiButton，间距由容器补）。
   仍在 slot 内容上生效，所以 `:deep()` 不能去掉 —— 这些按钮属于调用方的作用域。
   Still applies to slot content, so `:deep()` cannot be dropped — those buttons belong to the
   caller's scope. */
.card-body :deep(.ui-btn) { margin-top: var(--sp-3); }
</style>
