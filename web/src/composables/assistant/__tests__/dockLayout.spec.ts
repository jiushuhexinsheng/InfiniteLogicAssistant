import { describe, expect, it } from 'vitest'
import { BALL_SIZE, ballSide, dockStyle } from '../dockLayout'

/** 视口固定 1000x800，球默认停在右下（x = 920 表示球右缘贴边）。 */
const VIEWPORT = { w: 1000, h: 800 }

/**
 * 球心越过中线才算换边：这样球停在中间时不会来回抖。
 * The side only flips once the ball's centre crosses the midline, which keeps a ball parked
 * mid-screen from flipping back and forth.
 */
describe('ballSide 换边阈值', () => {
  it('球心在中线右侧 → right', () => {
    expect(ballSide({ x: 500, y: 0 }, VIEWPORT)).toBe('right')
  })

  it('球心在中线左侧 → left', () => {
    expect(ballSide({ x: 400, y: 0 }, VIEWPORT)).toBe('left')
  })

  it('球心正好压在中线 → left（不换边）', () => {
    expect(ballSide({ x: 500 - BALL_SIZE / 2, y: 0 }, VIEWPORT)).toBe('left')
  })
})

/**
 * 容器必须锚在球所在的那条边，否则胶囊一变宽球就会跟着挪。
 * The container must anchor to the ball's own edge, or a wider pill would drag the ball along.
 */
describe('dockStyle 锚点', () => {
  it('靠右：用 right 锚定，右缘等于球右缘', () => {
    const style = dockStyle({ x: 920, y: 720 }, VIEWPORT)
    expect(style.right).toBe(1000 - 920 - BALL_SIZE + 'px')
    expect(style.left).toBeUndefined()
  })

  it('靠左：用 left 锚定，左缘等于球左缘', () => {
    const style = dockStyle({ x: 40, y: 720 }, VIEWPORT)
    expect(style.left).toBe('40px')
    expect(style.right).toBeUndefined()
  })

  it('底部跟随球位置并钳在视口内', () => {
    expect(dockStyle({ x: 920, y: 720 }, VIEWPORT).bottom).toBe(800 - 720 - BALL_SIZE + 'px')
    expect(dockStyle({ x: 920, y: 2000 }, VIEWPORT).bottom).toBe('0px')
  })
})
