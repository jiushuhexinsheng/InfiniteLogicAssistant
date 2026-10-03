// @vitest-environment jsdom
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import QuestionBlock from '../QuestionBlock.vue'
import { makeBlock } from '../../../blocks/normalize'

/**
 * 问题块窄容器适配（修「悬浮窗的问题选择栏布局混乱没有适应小窗口」）：
 * 悬浮面板只有 368px，composite 的多个长选项一行排不下 —— 选项行必须允许换行，
 * 否则行内容溢出被 overflow:hidden 裁切、相邻按钮文字互相压盖（repro 实测
 * scrollWidth 345 > clientWidth 336）。
 *
 * jsdom 没有布局引擎，测不了 scrollWidth —— 样式规则对样式源断言（回归靶子），
 * 真实布局用 Playwright repro 复测。
 */
describe('QuestionBlock 窄面板布局', () => {
  /** 选项行必须允许换行：窄面板下按钮逐行排，不溢出裁切。 */
  it('选项行 flex-wrap: wrap（长选项不溢出窄面板）', () => {
    // jsdom 下 import.meta.url 非 file scheme，用测试文件自身路径定位被测组件。
    // import.meta.url is not a file scheme under jsdom; locate the component from the spec's own path.
    const specPath = expect.getState().testPath as string
    const src = readFileSync(join(dirname(specPath), '../QuestionBlock.vue'), 'utf8')
    const rule = src.match(/\.q-row\s*\{([^}]*)\}/)?.[1] ?? ''
    expect(rule).toMatch(/flex-wrap:\s*wrap/)
  })

  /** composite 长选项：选项行 + 输入行都渲染，按钮齐全（布局修复不破坏结构）。 */
  it('composite 渲染选项行与输入行', () => {
    const b = makeBlock('question', {
      qid: 'q1',
      question: '请确认如何执行这个任务？',
      kind: 'composite',
      options: [
        { value: 'open_ep', label: '打开B站《凡人修仙传》第112集播放页' },
        { value: 'play_latest', label: '播放番剧最新更新的一集' },
        { value: 'cancel', label: '取消本次任务' },
      ],
      status: 'pending',
    })
    const w = mount(QuestionBlock, { props: { block: b } })
    expect(w.findAll('.q-row')).toHaveLength(2)   // 选项行 + 输入行。Options row + input row.
    expect(w.findAll('.ui-btn')).toHaveLength(4)  // 3 选项 + 回答。3 options + submit.
    expect(w.text()).toContain('打开B站《凡人修仙传》第112集播放页')
  })
})
