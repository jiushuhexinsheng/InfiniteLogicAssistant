<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.8"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <template v-for="(el, i) in elements" :key="i">
      <path v-if="el.t === 'path'" :d="el.d" />
      <circle v-else-if="el.t === 'circle'" :cx="el.cx" :cy="el.cy" :r="el.r" />
    </template>
  </svg>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ICONS } from './icons'

const props = withDefaults(defineProps<{
  name: string
  size?: number
}>(), { size: 18 })

const elements = computed(() => ICONS[props.name] || [])
</script>
