// 手写 SVG 图标注册表（24×24 viewBox，描边风格）
export interface IconElement {
  t: 'path' | 'circle'
  d?: string          // path 数据
  cx?: number
  cy?: number
  r?: number          // circle 参数
}

const p = (d: string): IconElement => ({ t: 'path', d })
const c = (cx: number, cy: number, r: number): IconElement => ({ t: 'circle', cx, cy, r })

export const ICONS: Record<string, IconElement[]> = {
  // 状态
  wave: [p('M3 12c1.5 0 1.5-2 3-2s1.5 4 3 4 1.5-6 3-6 1.5 2 3 2 1.5-2 3-2'), p('M3 16c1.5 0 1.5-2 3-2s1.5 4 3 4 1.5-6 3-6 1.5 2 3 2 1.5-2 3-2')],
  ear: [p('M3 18v-6a9 9 0 0 1 18 0v6'), p('M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3z'), p('M3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z')],
  mic: [p('M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z'), p('M19 10v2a7 7 0 0 1-14 0v-2'), p('M12 19v4'), p('M8 23h8')],
  sparkles: [p('M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z'), p('M19 16l.9 2.1L22 19l-2.1.9L19 22l-.9-2.1L16 19l2.1-.9z')],
  brain: [p('M9.5 3a2.5 2.5 0 0 0-2.5 2.5 2 2 0 0 0-1 3.5A2 2 0 0 0 7 12a2 2 0 0 0-1 3.5 2 2 0 0 0 1 3.5A2.5 2.5 0 0 0 9.5 21V3z'), p('M14.5 3a2.5 2.5 0 0 1 2.5 2.5 2 2 0 0 1 1 3.5 2 2 0 0 1-1 3 2 2 0 0 1 1 3.5 2 2 0 0 1-1 3.5 2.5 2.5 0 0 1-2.5 2.5V3z'), p('M9.5 3h5M9.5 21h5')],
  wrench: [p('M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z')],
  chat: [p('M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z')],
  check: [p('M20 6L9 17l-5-5')],
  alert: [c(12, 12, 10), p('M12 8v4'), p('M12 16h.01')],
  // 工具
  search: [c(11, 11, 7), p('M21 21l-4.3-4.3')],
  send: [p('M22 2L11 13'), p('M22 2l-7 20-4-9-9-4z')],
  // 操作
  trash: [p('M3 6h18'), p('M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6'), p('M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2'), p('M10 11v6'), p('M14 11v6')],
  'chevron-down': [p('M6 9l6 6 6-6')],
  close: [p('M18 6L6 18'), p('M6 6l12 12')],
  play: [p('M5 3l14 9-14 9z')],
  stop: [p('M6 6h12v12H6z')],
  dots: [c(5, 12, 1.6), c(12, 12, 1.6), c(19, 12, 1.6)],
  user: [c(12, 8, 4), p('M4 21c0-4 3.6-6 8-6s8 2 8 6')],
}

export const ICON_NAMES = Object.keys(ICONS)
