#!/usr/bin/env node
/**
 * 界面截图 — 生成 README / wiki 用的页面图。
 *
 * UI screenshots — generates the page images used by the README and wiki.
 *
 * 用法 / Usage:
 *   cd web && npm run shot            # 开始页 → docs/images/start-page.png
 *   npm run shot -- --page console --out docs/images/console.png
 *   npm run shot -- --url http://127.0.0.1:5173   # 指向 dev server
 *
 * 前置 / Prerequisites: 后端已启动（python main.py serve）、本机已装 Chrome。
 * 用固定的视口尺寸（1440×900）与 deviceScaleFactor=2，保证每次生成同一规格的图 ——
 * 否则不同人跑出来的图大小不一，README 排版会跳。
 *
 * A fixed viewport (1440×900) with deviceScaleFactor=2 keeps every run the same size; otherwise
 * contributors produce differently-sized images and the README layout jumps around.
 */
import { mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { chromium } from 'playwright-core'

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..')

/** 命令行参数解析。Command-line argument parsing. */
function parseArgs(argv) {
  const out = {
    url: 'http://127.0.0.1:8520',
    page: 'start',
    out: '',
    width: 1440,
    height: 900,
    scale: 1,
    wake: false,
  }
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a === '--url') out.url = argv[++i]
    else if (a === '--page') out.page = argv[++i]
    else if (a === '--out') out.out = argv[++i]
    else if (a === '--scale') out.scale = Number(argv[++i])
    else if (a === '--wake') out.wake = true
  }
  return out
}

const ARGS = parseArgs(process.argv.slice(2))

/** 页面名 → 路由路径。Page name to route path. */
const PAGES = {
  start: '/',
  console: '/console',
}

const route = PAGES[ARGS.page] ?? ARGS.page
const outPath = resolve(REPO_ROOT, ARGS.out || `docs/images/${ARGS.page}-page.png`)

const browser = await chromium.launch({
  channel: 'chrome',
  headless: true,
  args: ['--use-fake-ui-for-media-stream', '--autoplay-policy=no-user-gesture-required'],
})
const ctx = await browser.newContext({
  permissions: ['microphone'],
  viewport: { width: ARGS.width, height: ARGS.height },
  // 默认 1×：README 正文栏约 860px 宽，1440px 的图已被缩小显示，再高的密度只是白占仓库
  // 体积（2× 的同一张图约 2.3MB，1× 约 0.5MB）。需要放大看细节时用 --scale 2。
  // Defaults to 1×: the README column is ~860px wide, so a 1440px image is already downscaled
  // and extra density only bloats the repo (the same shot is ~2.3MB at 2×, ~0.5MB at 1×). Pass
  // --scale 2 when the detail needs to survive zooming.
  deviceScaleFactor: ARGS.scale,
  locale: 'zh-CN',
})
const page = await ctx.newPage()

const errors = []
page.on('console', m => { if (m.type() === 'error') errors.push(m.text().slice(0, 160)) })

await page.goto(`${ARGS.url}${route}`, { waitUntil: 'domcontentloaded' })
// 等字体与首屏动画落定，否则截图会拍到加载态。
// Let fonts and the entry animation settle, or the shot catches a loading state.
await page.waitForTimeout(3000)

if (ARGS.wake) {
  await page.locator('text=开启语音唤醒').first().click().catch(() => {})
  await page.waitForTimeout(6000)   // 等 Vosk 模型就绪（已缓存时很快）
}

// 隐藏悬浮球上的拖拽残留与光标，避免截图带上焦点框。
// Blur so no focus ring is captured.
await page.evaluate(() => document.activeElement?.blur?.())
await page.waitForTimeout(300)

mkdirSync(dirname(outPath), { recursive: true })
await page.screenshot({ path: outPath })

console.log(`✓ 已保存 ${outPath}`)
console.log(`  页面 ${route}　视口 ${ARGS.width}×${ARGS.height} @${ARGS.scale}x`)
if (errors.length) console.log(`  ⚠️ 控制台报错 ${errors.length} 条：${errors.slice(0, 3).join(' | ')}`)

await browser.close()
