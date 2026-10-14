<template>
  <span class="ui-field-chevron" :class="{ open }"><UiIcon name="chevron-down" :size="14" /></span>
</template>

<!-- 字段控件触发器右侧的自绘 chevron 底座（圆底、开合旋转、展开时转品牌色）。
     Field-control trigger's custom chevron seat (round seat, rotates on toggle, turns brand-coloured
     when open).

     UiSelect 与 UiCombobox 原本各有一份**逐字相同**的模板 + 16 行样式，注释里还互相指认
     （`UiCombobox.vue` 旧注释：「镜像 UiSelect 的 .ui-select-chevron」）。Batch 8 抽弹层时留下了
     这一对，现在也收成一份 —— 做法与那次相同：行为留在组合式里，外观收进组件。

     UiSelect and UiCombobox each carried a verbatim copy — the same template plus 16 lines of CSS —
     with comments pointing at each other. Batch 8 left this pair behind when it extracted the panel;
     it is one implementation now, by the same recipe: behaviour stays in the composable, appearance
     moves into a component. -->
<script setup lang="ts">
import UiIcon from './UiIcon.vue'

/** chevron Props：面板是否展开。Chevron props: whether the panel is open. */
withDefaults(defineProps<{ open?: boolean }>(), { open: false })
</script>

<style scoped>
.ui-field-chevron {
  position: absolute; right: 6px; top: 50%;
  transform: translateY(-50%);
  width: 26px; height: 26px; border-radius: 50%;
  display: grid; place-items: center;
  background: var(--surface-control);
  color: var(--text-3);
  pointer-events: none;
  transition: transform var(--dur-base) var(--ease-out), color var(--dur-fast), background var(--dur-fast);
}
.ui-field-chevron.open {
  transform: translateY(-50%) rotate(180deg);
  color: var(--brand-c2);
  background: rgba(103, 232, 249, .12);
}
</style>
