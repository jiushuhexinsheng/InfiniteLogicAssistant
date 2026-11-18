<template>
  <!-- 浏览器硬件：输入/输出设备与三条音频处理开关。
       Browser hardware: input/output devices and three audio-processing toggles. -->
  <div class="cs-grid">
    <SettingsField label="输入设备" en="Input device">
      <UiSelect :model-value="s.ed().hardware.input_device" :options="inputOptions"
        placeholder="系统默认 / System default" @update:model-value="v => (s.ed().hardware.input_device = String(v))" />
    </SettingsField>
    <SettingsField label="输出设备" en="Output device">
      <UiSelect :model-value="s.ed().hardware.output_device" :options="outputOptions"
        placeholder="系统默认 / System default" @update:model-value="v => (s.ed().hardware.output_device = String(v))" />
    </SettingsField>
  </div>
  <div class="cs-grid">
    <SettingsField label="回声消除" en="Echo cancellation" row>
      <UiToggle :model-value="s.ed().hardware.echo_cancellation"
        @update:model-value="v => (s.ed().hardware.echo_cancellation = v)" />
    </SettingsField>
    <SettingsField label="降噪" en="Noise suppression" row>
      <UiToggle :model-value="s.ed().hardware.noise_suppression"
        @update:model-value="v => (s.ed().hardware.noise_suppression = v)" />
    </SettingsField>
    <SettingsField label="自动增益" en="Auto gain" row>
      <UiToggle :model-value="s.ed().hardware.auto_gain"
        @update:model-value="v => (s.ed().hardware.auto_gain = v)" />
    </SettingsField>
  </div>
  <UiButton variant="secondary" size="sm" @click="refreshDevices(true)">
    <BiLabel zh="刷新设备列表" en="Refresh devices" />
  </UiButton>
</template>

<script setup lang="ts">
/**
 * 浏览器硬件段（设备与音频处理），从 LocalModelsCard 拆出。
 * Browser hardware section (devices and audio processing), extracted from LocalModelsCard.
 */
import SettingsField from './SettingsField.vue'
import BiLabel from './BiLabel.vue'
import { UiButton, UiSelect, UiToggle } from '../../ui'
import { useSettings } from './useSettings'
import { useLocalModels } from './useLocalModels'

const s = useSettings()
const { inputOptions, outputOptions, refreshDevices } = useLocalModels()
</script>

<style scoped>
.cs-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--sp-2); }
</style>
