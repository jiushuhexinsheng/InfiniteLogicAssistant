/**
 * 漂浮单元（球 + 状态胶囊 + 迷你条）的摆放计算。
 *
 * 抽成纯函数是因为真实摆放依赖 window.innerWidth，组件里测不出边界；把「球在哪一侧、
 * 容器锚在哪条边」拆出来后，翻转规则可以穷尽断言。
 *
 * Placement math for the floating dock (ball + status pill + mini bar). It is pure because
 * the real layout reads window.innerWidth, which a component test cannot vary; splitting out
 * "which side is the ball on, which edge does the container anchor to" makes the flip rule
 * exhaustively testable.
 */

/** 视口尺寸。Viewport size. */
export interface Viewport {
  /** 视口宽度（px）。Viewport width in pixels. */
  w: number
  /** 视口高度（px）。Viewport height in pixels. */
  h: number
}

/** 球在视口中的左上角坐标。Ball position (top-left corner) in the viewport. */
export interface Pos {
  x: number
  y: number
}

/** 悬浮球直径（px），与 FloatBall 的宽高一致。Floating ball diameter in pixels, matching FloatBall. */
export const BALL_SIZE = 56

/**
 * 球所在的一侧：球心越过视口中线即算靠右。
 *
 * 状态胶囊与迷你条总挂在球的**内侧**（朝屏幕中间），所以球贴左/贴右都不会有东西被裁掉。
 *
 * Which half the ball sits in: once the ball's centre crosses the viewport midline it counts
 * as right. The status pill and mini bar always hang on the ball's inner side (towards the
 * middle of the screen), so nothing gets clipped when the ball sits against an edge.
 *
 * @param pos 球左上角坐标。Ball top-left position.
 * @param viewport 视口尺寸。Viewport size.
 * @returns 球所在的一侧。The side the ball sits in.
 */
export function ballSide(pos: Pos, viewport: Viewport): 'left' | 'right' {
  return pos.x + BALL_SIZE / 2 > viewport.w / 2 ? 'right' : 'left'
}

/**
 * 漂浮容器的定位样式。
 *
 * 靠右时用 `right` 锚定（容器右缘 = 球右缘），靠左时用 `left` 锚定（容器左缘 = 球左缘）：
 * 这样 flex 只需决定行方向，胶囊/消息条宽度变化不会挪动球本身。
 *
 * Inline style for the dock container. Anchored by `right` when the ball is on the right
 * (dock right edge = ball right edge) and by `left` otherwise (dock left edge = ball left
 * edge), so flex only has to pick the row direction and the ball never shifts when the pill
 * or the mini bar changes width.
 *
 * @param pos 球左上角坐标。Ball top-left position.
 * @param viewport 视口尺寸。Viewport size.
 * @returns 定位样式（inline style 对象）。Positioning style as an inline style object.
 */
export function dockStyle(pos: Pos, viewport: Viewport): Record<string, string> {
  const bottom = Math.max(0, viewport.h - pos.y - BALL_SIZE) + 'px'
  if (ballSide(pos, viewport) === 'right') {
    return { right: Math.max(0, viewport.w - pos.x - BALL_SIZE) + 'px', bottom }
  }
  return { left: Math.max(0, pos.x) + 'px', bottom }
}
