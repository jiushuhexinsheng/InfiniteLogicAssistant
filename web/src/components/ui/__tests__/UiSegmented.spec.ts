// @vitest-environment jsdom
/** 分段单选：stack 布局下英文另起一行，相同英文省略。 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import UiSegmented from '../UiSegmented.vue'

const OPTS = [
  { value: 'local', label: '本地', en: 'Local' },
  { value: 'cloud', label: 'API', en: 'API' },
]

describe('UiSegmented', () => {
  it('默认 inline：不渲染英文行', () => {
    const w = mount({
      components: { UiSegmented },
      template: '<UiSegmented v-model="v" :options="opts" />',
      setup: () => ({ v: ref('local'), opts: OPTS }),
    })
    expect(w.findAll('.sg-en')).toHaveLength(0)
  })

  it('stack：英文在下一行，英文与中文相同则省略', () => {
    const w = mount({
      components: { UiSegmented },
      template: '<UiSegmented v-model="v" :options="opts" layout="stack" />',
      setup: () => ({ v: ref('local'), opts: OPTS }),
    })
    const ens = w.findAll('.sg-en').map(e => e.text())
    expect(ens).toEqual(['Local'])
  })
})
