<template>
  <!-- 虚线占位框：非文本块共用的「虚线 + 圆角 + 底」三件套（思考 / 文件 / 图片 / 未知块）。
       原先这 3 条声明在四个组件里各写一份，改一处要记得同步另外三处；抽出来后
       「虚线框长什么样」只有一处 —— 视觉批要重做它的质感时是一处编辑，不是四处。

       Dashed placeholder frame: the shared triple (dashed border + radius + fill) of the
       non-text blocks (thinking / file / image / unknown). The three declarations used to be
       copied into four components; now "what a dashed frame looks like" lives in one place,
       so a visual pass restyles one file instead of four. -->
  <div class="ui-hint"><slot /></div>
</template>

<!-- 只负责那三件套，**不含**内边距与布局：各块的 padding / flex / 排版差异是刻意的
     （文件与图片是横排、思考是块级；内边距 8 / 12 / 16 各不相同），由调用方用自己的
     scoped 样式给 —— 调用方的 scoped 选择器能命中本组件根元素（Vue 会把父组件的 scope
     属性加到子组件根上），所以像 `.blk-file { padding: … }` 这样写仍然生效。

     Only the triple — no padding, no layout. The per-block differences are deliberate
     (file/image are flex rows, thinking is block; paddings are 8/12/16), so callers supply
     them via their own scoped styles, which do reach this root element (Vue applies the
     parent's scope attribute to a child component's root). -->
<style scoped>
.ui-hint {
  border: 1px dashed var(--bg-3);
  border-radius: var(--r-md);
  background: var(--bg-1);
}
</style>
