import { describe, expect, it } from 'vitest'
import { stripMarkdown, speechForBlocks, splitSentences } from '../speech'
import { makeBlock } from '../normalize'
import '../index'  // 注册副作用 Registration side effects

/** 语音播报管线：markdown 剥离、块级播报策略、回合统一出口。
 *  Speech pipeline: markdown stripping, per-block policy, unified turn exit. */
describe('speech 播报管线', () => {
  /** markdown 记号不被念出来（修复点）。Markdown tokens are not read aloud. */
  it('stripMarkdown 剥离记号', () => {
    expect(stripMarkdown('**粗体** 和 *斜体*')).toBe('粗体 和 斜体')
    expect(stripMarkdown('[链接文字](https://x.com)')).toBe('链接文字')
    expect(stripMarkdown('`code` 片段')).toBe('code 片段')
    expect(stripMarkdown('# 标题\n- 列表项')).toBe('标题 列表项')
  })

  /** 代码围栏降级为「代码块」提示，不念代码本体。
   *  Code fences degrade to a hint; the code body is not read. */
  it('代码围栏不念代码本体', () => {
    const s = stripMarkdown('看这段：\n```python\nprint(secret)\n```\n完毕')
    expect(s).not.toContain('print')
    expect(s).toContain('代码块')
  })

  /** thinking 默认不播、text 播剥离后正文。thinking silent; text speaks stripped body. */
  it('块级播报策略：thinking 静音、text 播正文', () => {
    const speech = speechForBlocks([
      makeBlock('thinking', { text: '内心戏' }),
      makeBlock('text', { md: '**结论**是晴天' }),
    ])
    expect(speech).not.toContain('内心戏')
    expect(speech).toContain('结论是晴天')
    expect(speech).not.toContain('**')
  })

  /** summary.tts_text 是权威出口（回合播报一次、内容可预期）。
   *  summary.tts_text is the authoritative exit. */
  it('summary.tts_text 优先作为回合播报出口', () => {
    const speech = speechForBlocks([
      makeBlock('text', { md: '正文内容' }),
      makeBlock('summary', { summary_text: '汇总原文', tts_text: '已查天气，晴，26度' }),
    ])
    expect(speech).toBe('已查天气，晴，26度')
  })

  /** 无 summary 时 tool/answer/unknown 静音。Without a summary, tool/answer/unknown are silent. */
  it('tool/answer 默认不播', () => {
    const speech = speechForBlocks([
      makeBlock('tool', { name: 'run_shell_tool', output: 'x' }),
      makeBlock('answer', { text: '上海' }),
    ])
    expect(speech).toBe('')
  })
})

/** 句级切分（句级流式 TTS 的入队粒度）。Sentence splitting (enqueue granularity of
 *  sentence-streaming TTS). */
describe('splitSentences', () => {
  /** 终结符断句 + 右引号归位 + 空输入。Delim split, closing quote kept, empty input. */
  it('按终结符断句，空输入返回空数组', () => {
    expect(splitSentences('')).toEqual([])
    expect(splitSentences('   ')).toEqual([])
    expect(splitSentences('第一句话已经说完了。明天会继续下雨吗？')).toEqual([
      '第一句话已经说完了。', '明天会继续下雨吗？',
    ])
    expect(splitSentences('他说"出发吧"。然后我们就走了。')).toEqual([
      '他说"出发吧"。', '然后我们就走了。',
    ])
  })

  /** 超长句按逗号二分，单句不超过上限。Overlong sentences halve on commas. */
  it('超长句二分且每句不超过上限', () => {
    const long = ('这是一个很长的句子需要被切开，因为它实在太长了，'.repeat(6))
    const parts = splitSentences(long)
    expect(parts.length).toBeGreaterThan(1)
    for (const p of parts) expect(p.length).toBeLessThanOrEqual(120)
    expect(parts.join('')).toBe(long)
  })

  /** 尾句过短并入前句（避免孤字尾音）。Short tail merges into the previous sentence. */
  it('短尾句并入前句', () => {
    expect(splitSentences('第一句话已经说完了。好。')).toEqual(['第一句话已经说完了。好。'])
  })
})
