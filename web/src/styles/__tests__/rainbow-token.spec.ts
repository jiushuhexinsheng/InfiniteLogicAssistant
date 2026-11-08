/**
 * 彩虹激活态令牌的静态护栏。
 *
 * 背景：聆听/录音时面板与悬浮球都用 `var(--rainbow)` + `animation: rainbow-hue`，
 * 但两者**全仓从未定义** —— 浏览器把整个 `background` 声明判为无效，彩虹边框静默消失。
 * 这类「变量缺失」不会报错、也不会被单元测试发现，只能靠读 CSS 源码守住。
 *
 * Static guard for the rainbow activation token.
 * Why: in the listening/recording state both the panel and the floating ball use
 * `var(--rainbow)` + `animation: rainbow-hue`, but neither was ever defined anywhere in
 * the repo — the browser drops the entire `background` declaration and the rainbow border
 * vanishes silently. A missing custom property raises no error and no runtime test can see
 * it, so this reads the CSS source directly.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const ROOT = resolve(__dirname, '../../..')
const read = (p: string) => readFileSync(resolve(ROOT, p), 'utf8')

describe('rainbow activation token', () => {
  it('tokens.css registers the rotating angle and the rainbow-hue keyframes', () => {
    const css = read('src/styles/tokens.css')
    // @property 让 @keyframes 能平滑插值 <angle>；没有注册也能显示静态彩虹，但动画失效。
    expect(css).toMatch(/@property\s+--rainbow-angle\s*\{[^}]*syntax:\s*['"]<angle>['"]/)
    expect(css).toMatch(/@keyframes\s+rainbow-hue\s*\{/)
    expect(css).toMatch(/--rainbow-angle:\s*360deg/)
  })

  it.each([
    ['src/components/assistant/AssistantPanel.vue', '.float-panel.fx-rainbow'],
    ['src/components/assistant/FloatBall.vue', '.float-trigger.fx-rainbow'],
  ])('%s defines --rainbow as a conic gradient on the animated element', (file, selector) => {
    const src = read(file)
    const rule = src.slice(src.indexOf(selector))
    expect(rule).toContain('var(--rainbow)')
    // 变量必须声明在**动画元素自身**上，否则 conic-gradient 里的角度会在 :root 处定格。
    expect(rule).toMatch(/--rainbow:\s*conic-gradient\(/)
  })
})
