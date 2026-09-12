<template>
  <Teleport to="body">
    <div v-if="items.length" class="ui-toaster">
      <div
        v-for="t in items"
        :key="t.id"
        class="ui-toast"
        :class="'k-' + t.kind"
        @click="notify.dismiss(t.id)"
      >
        {{ t.text }}
      </div>
    </div>
  </Teleport>
</template>

<!-- 全局通知浮层：Teleport 到 body，z-index 高于悬浮球（9999）以保证可见。Global notification overlay: teleported to body, z-index above the floating ball (9999) so it stays visible. -->
<script setup lang="ts">
import { notify, useToast } from '../../composables/useToast'

/** 通知队列（模块级单例）。The notification queue (module-level singleton). */
const { items } = useToast()
</script>

<style scoped>
.ui-toaster {
  position: fixed; right: 18px; bottom: 18px; z-index: 10000;
  display: flex; flex-direction: column; gap: var(--sp-2); align-items: flex-end;
  pointer-events: none;
}
.ui-toast {
  font-size: var(--fs-xs); max-width: 420px; cursor: pointer;
  border-radius: var(--r-sm); padding: var(--sp-2) var(--sp-3);
  border: 1px solid var(--border-soft); background: var(--surface-raised);
  color: var(--text-1); pointer-events: auto;
  box-shadow: var(--shadow-3);
  animation: ui-toast-in var(--dur-fast) ease-out;
}
.ui-toast.k-ok { color: var(--ok); border-color: rgba(52, 211, 153, .4); }
.ui-toast.k-err { color: var(--err); border-color: rgba(248, 113, 113, .4); }
.ui-toast.k-warn { color: var(--warn); border-color: rgba(251, 191, 36, .4); }
.ui-toast.k-info { color: var(--text-2); }

@keyframes ui-toast-in {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
