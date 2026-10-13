#!/usr/bin/env node
/**
 * 全站截图基线 —— 重构期的视觉回归护栏。
 *
 * Full-surface screenshot baseline — the visual-regression guard for refactors.
 *
 * 为什么需要它：全仓 63 个 spec 里没有任何视觉回归测试，`.design-audit/` 在仓外，
 * `screenshot.mjs` 只覆盖 2 个页面。没有基线，「外观不变」这条硬约束无法被验证，
 * 只能靠人眼 —— 而人眼对 40px→30px 这类漂移不敏感。
 * Why: none of the 63 specs is a visual-regression test, `.design-audit/` lives outside the
 * repo, and `screenshot.mjs` covers only 2 pages. Without a baseline, "the look didn't
 * change" cannot be verified — and the eye is not sensitive to 40px→30px drifts.
 *
 * 用法 / Usage:
 *   npm run shot:all -- --baseline                  # 存基线 → web/.shots/base/
 *   npm run shot:all -- --compare                   # 与基线逐张比对
 *   npm run shot:all -- --url http://localhost:5173 # 指向 dev server（默认后端 :8520）
 *   npm run shot:all -- --baseline --only status    # 只跑名字含 status 的几张
 *
 * 前置 / Prereq: 已起 vite dev(:5173) 或后端(:8520)；本机已装 Chrome。
 * 输出到 web/.shots/（gitignore）—— 绝不写 docs/images/，那是已提交的 README 用图。
 * Output goes to web/.shots/ (gitignored) — never docs/images/, which holds committed
 * README images.
 */
import { mkdirSync, readFileSync, writeFileSync, existsSync, readdirSync } from 'node:fs'
import { dirname, resolve, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createHash } from 'node:crypto'

import { chromium } from 'playwright-core'

const WEB_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const SHOTS_DIR = join(WEB_ROOT, '.shots')

/**
 * 解析命令行参数。Parse command-line arguments.
 * @returns 参数对象。The parsed options object.
 */
function parseArgs(argv) {
  // tolerance 默认 8：浏览器的文字抗锯齿偶发产生 1-2 个像素的抖动（实测 console-tools 出现过
  // 1 像素差异），这在 1.3M 像素里是 0.0001%，属渲染噪声而非变化。**不静默放宽** —— 落在容差内
  // 的差异照样逐条打印实际像素数。
  // tolerance defaults to 8: the browser's text antialiasing occasionally jitters a pixel or two
  // (console-tools was observed differing by 1 pixel) — 0.0001% of 1.3M pixels, rendering noise
  // rather than change. **Not a silent relaxation**: in-tolerance differences are still printed
  // with their actual pixel counts.
  const out = { url: 'http://127.0.0.1:8520', mode: '', only: '', settle: 1000, tolerance: 8 }
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a === '--baseline') out.mode = 'baseline'
    else if (a === '--compare') out.mode = 'compare'
    else if (a === '--url') out.url = argv[++i]
    else if (a === '--only') out.only = argv[++i]
    else if (a === '--settle') out.settle = Number(argv[++i])
    else if (a === '--tolerance') out.tolerance = Number(argv[++i])
  }
  return out
}

const ARGS = parseArgs(process.argv.slice(2))
if (!ARGS.mode) {
  console.error('用法/Usage: npm run shot:all -- --baseline | --compare [--url ...] [--only ...]')
  process.exit(2)
}

/** 控制台 11 个标签页的 key ↔ 侧栏中文标签。要点击侧栏切换（不注入 activeTab），
 *  这样跑的是用户真实路径，而不是给产品代码开后门。
 *  The 11 console tabs' key ↔ sidebar label. Clicked via the sidebar (activeTab is never
 *  injected), so this exercises the real user path rather than a back door. */
const CONSOLE_TABS = [
  ['conv', '对话'], ['task', '任务'], ['status', '状态'], ['tools', '工具'],
  ['stats', '统计'], ['env', '环境'], ['memory', '记忆'], ['settings', '设置'],
  ['history', '历史'], ['library', '任务库'], ['schedule', '定时'],
]

/** 设置页左侧 6 个菜单（configDefs.menuDefs 的 label）。Six settings menus. */
const SETTINGS_MENUS = ['大模型', '语音识别', '语音合成', '语音唤醒', '权限', '高级设置']

/** 空态截图：列表端点桩成空，拍那些有数据时不可见的分支。
 *  Empty-state shots: list endpoints stubbed empty to capture branches invisible with data. */
const EMPTY_SHOTS = [
  ['empty-tools', '工具', { '**/api/tools': { ok: true, tools: [] } }],
  ['empty-memory', '记忆', { '**/api/memory': { ok: true, facts: [] } }],
  ['empty-env', '环境', { '**/api/env': { ok: true, content: '' } }],
  ['empty-library', '任务库', { '**/api/library': { ok: true, tasks: [] } }],
  ['empty-schedule', '定时', { '**/api/schedules': { ok: true, schedules: [] } }],
  ['empty-history', '历史', { '**/api/sessions': { ok: true, sessions: [] } }],
].map(([name, label, stub]) => ({
  name, path: '/console', stub,
  act: async (page) => { await clickNav(page, label) },
}))

/** 截图清单：每项一个 recipe。step 抛错只记录不中断 —— 一张拍失败不该让整轮泡汤。
 *  The shot list: one recipe per entry. A failing step is recorded, not fatal — one bad
 *  shot must not sink the whole run. */
const SHOTS = [
  {
    name: 'start',
    path: '/',
    /** 起始页「后端」那一行显示实测延迟（每次跑都不同，实测漂移 7×8px）——遮掉，
     *  否则 diff 被数据噪声淹没。它是 `checkPing` 的产物，与设计无关。
     *  The start page's 后端 row shows a measured latency (differs every run; measured drift
     *  was a 7×8px box). Masked, or data noise drowns the diff — it's `checkPing` output,
     *  nothing to do with design. */
    mask: ['.service-item:last-child'],
  },
  {
    // 整页截图：起始页在 900px 视口下只露到卡片中部，特性网格与页脚都在折叠线以下 ——
    // 视口截图拍不到它们，而 Batch 5 恰恰动了这两块。
    // 注意**不能用 fullPage**：滚动发生在 App.vue 的 `.app-view`（`height:100dvh` +
    // `overflow-y:auto`）里，文档本身不滚，fullPage 只会原样返回视口尺寸。改用加高视口，
    // 让整页一次入画。
    // Full-page shot: at a 900px viewport the start page only shows down to the middle of the
    // cards; the feature grid and footer sit below the fold — and Batch 5 changed exactly those.
    // **fullPage does not work here**: scrolling happens inside App.vue's `.app-view`
    // (`height:100dvh` + `overflow-y:auto`), the document itself never scrolls, so fullPage
    // just returns the viewport size. A taller viewport brings the whole page into one frame.
    name: 'start-full',
    path: '/',
    viewportHeight: 1400,
    mask: ['.service-item:last-child'],
  },
  { name: 'console-start-here', path: '/console' },
  ...CONSOLE_TABS.map(([key, label]) => ({
    name: `console-${key}`,
    path: '/console',
    /** 点侧栏导航项。Click the sidebar nav item. */
    act: async (page) => { await clickNav(page, label) },
    /** 状态 tab 的 `.ping-ms` 是同一份实测延迟，同理遮掉。 */
    mask: key === 'status' ? ['.ping-ms'] : [],
  })),
  { name: 'panel-expanded', path: '/console', act: async (page) => { await page.locator('.float-trigger').first().click() } },
  ...SETTINGS_MENUS.map((label) => ({
    name: `settings-${label}`,
    path: '/console',
    act: async (page) => { await clickNav(page, '设置'); await clickSettingsMenu(page, label) },
    /** 设置卡由 config 驱动，等它真出现再拍（见 settle 的注释）。The settings card is config-driven; wait for it to actually appear. */
    waitFor: '.cs-card',
  })),
  {
    // 滚动态：把设置卡体滚到底。抽取卡外壳时最容易弄坏的就是「卡体自滚、卡头不动、页面不动」
    // ——初始渲染的像素比对验不了这个，只有滚起来才看得出。
    // Scrolled state: scroll the settings card body to the bottom. The thing most easily broken
    // when extracting the card shell is "body scrolls, head stays put, page doesn't move" —
    // a pixel diff of the initial render cannot see that; only scrolling reveals it.
    name: 'settings-scrolled',
    path: '/console',
    act: async (page) => {
      await clickNav(page, '设置')
      await page.locator('.cs-card-body').first().evaluate(el => { el.scrollTop = el.scrollHeight })
    },
    waitFor: '.cs-card-body',
  },
  {
    // 下拉开态：UiSelect 的**选项列表**只在面板打开时才进 DOM，关态截图完全拍不到它。
    // 等 `.ui-select-menu` 出现 —— 若 options 传空，openMenu 会告警且不开面板，这里会超时，
    // 截图即暴露迁移漏配。
    // Open dropdown: UiSelect's **option list** only enters the DOM once the panel opens, so no
    // closed-state shot can see it. Waiting on `.ui-select-menu` doubles as the guard — with empty
    // `options` openMenu warns and never opens, the wait times out, and the shot exposes it.
    name: 'settings-select-open',
    path: '/console',
    act: async (page) => {
      await clickNav(page, '设置')
      await page.locator('.cs-main .ui-select').first().click()
    },
    waitFor: '.ui-select-menu',
  },
  ...EMPTY_SHOTS,
]

/**
 * 点侧栏导航项（按标签精确匹配，避免「任务」误中「任务库」）。
 * Click a sidebar nav item (exact label match, so 任务 doesn't hit 任务库).
 * @param page playwright 页面。The playwright page.
 * @param label 导航标签。The nav label.
 */
async function clickNav(page, label) {
  await page.locator('.sb-nav .ui-nav-item').filter({ hasText: new RegExp(`^${label}$`) }).first().click()
}

/**
 * 点设置页左侧菜单项。菜单是 ConsoleSettings 内联渲染的按钮，按文本精确匹配。
 * Click a settings left-menu item; the menu is rendered inline by ConsoleSettings.
 * @param page playwright 页面。The playwright page.
 * @param label 菜单标签。The menu label.
 */
async function clickSettingsMenu(page, label) {
  await page.locator('.cs-menu button, .cs-menu-item, .cs-menu [role="button"]')
    .filter({ hasText: new RegExp(`^${label}$`) }).first().click()
}

/**
 * 让页面进入确定性状态 —— 这是整套基线成立的前提。
 * Force the page into a deterministic state — the precondition for any baseline.
 *
 * 三件事：动画压到 .01ms（app.css 的 prefers-reduced-motion 块）、等网络静默、
 * 再等一个固定沉降期把懒加载与字体落定。缺任何一件，diff 都会被动画/加载态污染。
 *
 * @param page playwright 页面。The playwright page.
 */
async function settle(page, ms) {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  // 先给 SPA 一点时间挂载并**发出**首屏请求。少了这一步，networkidle 可能在请求发出之前就
  // 判定空闲 —— 那正是 settings-高级设置 偶发拍成空白卡的根因（config 尚未回来，editable 仍为
  // null，于是设置页一张卡都不渲染）。
  // Give the SPA a beat to mount and *issue* its first requests. Without this, networkidle can
  // resolve before they're sent — the root cause of the occasional blank settings-高级设置 shot
  // (config hadn't returned, editable was still null, so no card rendered).
  await page.waitForTimeout(400)
  await page.waitForLoadState('networkidle').catch(() => {})
  await page.waitForTimeout(ms)
  // 失焦，避免截图带上焦点环（与 screenshot.mjs 同策略）。
  // Blur so no focus ring is captured (same policy as screenshot.mjs).
  await page.evaluate(() => document.activeElement?.blur?.())
  await page.waitForTimeout(120)
}

/** 计算文件 sha256。Hash a file with sha256. */
function hashOf(buf) {
  return createHash('sha256').update(buf).digest('hex')
}

/**
 * 用浏览器自身做像素级比对 —— 不引入任何依赖（pngjs/pixelmatch 都没装）。
 * Pixel-diff by driving the browser itself — zero extra dependencies (neither pngjs nor
 * pixelmatch is installed).
 *
 * @param browser playwright 浏览器实例。The playwright browser.
 * @param a 基线 PNG buffer。Baseline PNG buffer.
 * @param b 当前 PNG buffer。Current PNG buffer.
 * @returns {Promise<{sizeMismatch?: boolean, total?: number, diff?: number, box?: number[]}>} 差异摘要。Diff summary.
 */
async function pixelDiff(browser, a, b) {
  const page = await browser.newPage()
  try {
    return await page.evaluate(async ([da, db]) => {
      /** 把 data URL 载成可绘制的 Image。Load a data URL into a drawable Image. */
      const load = (src) => new Promise((res, rej) => {
        const img = new Image()
        img.onload = () => res(img)
        img.onerror = () => rej(new Error('image decode failed'))
        img.src = src
      })
      const [ia, ib] = await Promise.all([load(da), load(db)])
      if (ia.width !== ib.width || ia.height !== ib.height) {
        return { sizeMismatch: true, a: [ia.width, ia.height], b: [ib.width, ib.height] }
      }
      const c = document.createElement('canvas')
      c.width = ia.width; c.height = ia.height
      const g = c.getContext('2d', { willReadFrequently: true })
      g.drawImage(ia, 0, 0)
      const pa = g.getImageData(0, 0, c.width, c.height).data
      g.clearRect(0, 0, c.width, c.height)
      g.drawImage(ib, 0, 0)
      const pb = g.getImageData(0, 0, c.width, c.height).data
      let diff = 0, minX = Infinity, minY = Infinity, maxX = -1, maxY = -1
      for (let i = 0; i < pa.length; i += 4) {
        if (pa[i] !== pb[i] || pa[i + 1] !== pb[i + 1] || pa[i + 2] !== pb[i + 2] || pa[i + 3] !== pb[i + 3]) {
          diff++
          const px = (i >> 2) % c.width, py = ((i >> 2) / c.width) | 0
          if (px < minX) minX = px
          if (py < minY) minY = py
          if (px > maxX) maxX = px
          if (py > maxY) maxY = py
        }
      }
      return { total: c.width * c.height, diff, box: maxX >= 0 ? [minX, minY, maxX, maxY] : null }
    }, [a.toString('base64').replace(/^/, 'data:image/png;base64,'), b.toString('base64').replace(/^/, 'data:image/png;base64,')])
  } finally {
    await page.close()
  }
}

// ── 主流程 ────────────────────────────────────────────────────────────────────
const outDir = join(SHOTS_DIR, ARGS.mode === 'baseline' ? 'base' : 'current')
mkdirSync(outDir, { recursive: true })

const browser = await chromium.launch({
  channel: 'chrome',
  headless: true,
  args: ['--use-fake-ui-for-media-stream', '--autoplay-policy=no-user-gesture-required'],
})
const ctx = await browser.newContext({
  permissions: ['microphone'],
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 1,   // 1× —— 基线图不追求清晰度，追求可比性。1× keeps shots comparable, not pretty.
  locale: 'zh-CN',
  colorScheme: 'dark',
})

const targets = ARGS.only ? SHOTS.filter(s => s.name.includes(ARGS.only)) : SHOTS
const results = []
const consoleErrors = []

for (const shot of targets) {
  const page = await ctx.newPage()
  const errs = []
  page.on('console', m => { if (m.type() === 'error') errs.push(m.text().slice(0, 200)) })
  let note = ''
  try {
    // 空态桩：把指定端点换成空数据，用来截那些「有数据时根本不会渲染」的分支。
    // 实测确认过这个必要性：工具 tab 的普通基线截到的是 11 个工具的列表，不是空态。
    // Empty-state stubs: replace endpoints with empty payloads so branches that never render
    // when data exists can still be captured. Verified as necessary — the plain tools baseline
    // shows the 11-tool list, not the empty state.
    for (const [pattern, body] of Object.entries(shot.stub || {})) {
      await page.route(pattern, r => r.fulfill({
        status: 200, contentType: 'application/json', body: JSON.stringify(body),
      }))
    }
    // 每张图可以覆盖视口高度（宽度固定 1440，与基线一致）。Per-shot viewport height override (width stays 1440 to match the baselines).
    if (shot.viewportHeight) await page.setViewportSize({ width: 1440, height: shot.viewportHeight })
    await page.goto(`${ARGS.url}${shot.path}`, { waitUntil: 'domcontentloaded' })
    await settle(page, ARGS.settle)
    if (shot.act) {
      await shot.act(page)
      // 内容就绪条件：等某个元素真正出现，别靠「等够久」赌它渲染完了。
      // Readiness condition: wait for a specific element rather than betting a fixed delay was
      // long enough.
      if (shot.waitFor) {
        await page.locator(shot.waitFor).first().waitFor({ timeout: 8000 }).catch(() => {})
      }
      await settle(page, ARGS.settle)
    }
  } catch (e) {
    note = `step failed: ${e.message.split('\n')[0]}`
  }
  const file = join(outDir, `${shot.name}.png`)
  // 遮掉随实时数据变化的元素（延迟读数等）—— 它们每次跑都不同。选择器匹配不到就跳过，
  // 不让一个失效的选择器炸掉整轮。
  // Mask live-data elements (latency readouts) — they differ every run. Missing selectors are
  // skipped so one stale selector can't sink the run.
  const masks = []
  for (const sel of shot.mask || []) {
    const loc = page.locator(sel)
    if ((await loc.count()) > 0) masks.push(loc)
  }
  await page.screenshot({ path: file, mask: masks, fullPage: shot.fullPage === true })
  await page.close()
  if (errs.length) consoleErrors.push(`${shot.name}: ${errs.slice(0, 2).join(' | ')}`)
  results.push({ name: shot.name, file, note })
  process.stdout.write(`  ${note ? '⚠️' : '✓'} ${shot.name}${note ? `  (${note})` : ''}\n`)
}

// ── 比对 / 汇总 ───────────────────────────────────────────────────────────────
if (ARGS.mode === 'baseline') {
  console.log(`\n基线已存 → ${outDir}`)
  console.log(`  共 ${results.length} 张。再跑一次 --baseline 应得到逐字节相同的产物。`)
  console.log(`  Re-run --baseline: the output must be byte-identical or the baseline is unusable.`)
} else {
  const bad = []
  const noisy = []
  for (const r of results) {
    const base = join(SHOTS_DIR, 'base', `${r.name}.png`)
    if (!existsSync(base)) { bad.push({ name: r.name, kind: 'no-baseline' }); continue }
    const a = readFileSync(base), b = readFileSync(r.file)
    if (hashOf(a) === hashOf(b)) continue                      // 快路径：字节相同即无差异。
    const d = await pixelDiff(browser, a, b)
    if (d.sizeMismatch) { bad.push({ name: r.name, kind: 'size', a: d.a, b: d.b }); continue }
    if (d.diff > ARGS.tolerance) bad.push({ name: r.name, kind: 'pixels', diff: d.diff, total: d.total, box: d.box })
    else if (d.diff > 0) noisy.push({ name: r.name, diff: d.diff, total: d.total, box: d.box })
  }
  if (!bad.length) {
    console.log(`\n✓ ${results.length} 张全部与基线一致（容差 ${ARGS.tolerance} 像素）。`)
  } else {
    console.log(`\n✗ ${bad.length}/${results.length} 张与基线不一致：`)
    for (const x of bad) {
      if (x.kind === 'no-baseline') console.log(`  · ${x.name} —— 基线缺失`)
      else if (x.kind === 'size') console.log(`  · ${x.name} —— 尺寸变了 ${x.a?.join('×')} → ${x.b?.join('×')}`)
      else console.log(`  · ${x.name} —— 差异 ${x.diff}/${x.total} 像素 (${(x.diff / x.total * 100).toFixed(3)}%)，区域 ${x.box ? x.box.join(',') : '-'}`)
    }
    console.log(`\n  当前图在 ${outDir}/ ，基线在 ${join(SHOTS_DIR, 'base')}/ —— 逐张对照。`)
    process.exitCode = 1
  }
  // 容差内的差异也照实打印 —— 让「1 像素噪声」和「真变化」在报告里分得开。
  // In-tolerance differences are printed too, so "1px noise" and "a real change" stay
  // distinguishable in the report.
  if (noisy.length) {
    console.log(`\n~ ${noisy.length} 张有容差内噪声（≤ ${ARGS.tolerance} 像素，视为渲染抗锯齿抖动）：`)
    for (const x of noisy) console.log(`  · ${x.name} —— ${x.diff}/${x.total} 像素，区域 ${x.box ? x.box.join(',') : '-'}`)
  }
}

if (consoleErrors.length) {
  console.log(`\n⚠️ 页面控制台报错 ${consoleErrors.length} 处：`)
  for (const e of consoleErrors.slice(0, 8)) console.log(`  · ${e}`)
}

await browser.close()
