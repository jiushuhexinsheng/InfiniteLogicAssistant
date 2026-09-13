#!/usr/bin/env node
/**
 * 语音验收台 — P6「语音作答 / 无应答待机 / 再唤醒续答 / 播报期不自触发」4 条人工验收项的
 * 自动化辅助。
 *
 * Voice acceptance harness — an automated assistant for the 4 manual P6 acceptance items
 * (voice answering / standby on silence / resume-on-wake / no self-trigger while speaking).
 *
 * 为什么需要它：这 4 项都需要真人对着麦克风说话、用耳朵听播报，无法用 Vitest 替代
 * （Vosk 是浏览器 WASM 引擎，测不到真实音频）。但「谁对谁错」的**判据**大部分是客观的
 * —— 状态机有没有进 standby、有没有发 /voice/answer、播报期间唤醒引擎有没有停 —— 这些
 * 可以自动采集。于是本脚本负责搭场景、采证据、判客观项，人只负责出声和听声。
 *
 * Why this exists: the 4 items need a human at the microphone and ears on the speaker and
 * cannot be replaced by Vitest (Vosk is a browser WASM engine; Vitest cannot drive real
 * audio). But most of the *verdicts* are objective — did the state machine enter standby,
 * was /voice/answer issued, was the wake engine stopped during playback — and those can be
 * captured automatically. So the harness builds the scenario, collects the evidence and
 * decides the objective parts; the human only has to make sound and listen.
 *
 * 用法 / Usage:
 *   cd web && npm run verify:voice                  # 默认 http://127.0.0.1:8520
 *   npm run verify:voice -- --url http://127.0.0.1:5173
 *   npm run verify:voice -- --skip 4                # 跳过某项
 *
 * 前置 / Prerequisites:
 *   - 后端已启动且前端已构建（python main.py serve），或 vite dev server 在跑
 *   - 本机有可用麦克风与扬声器，且**音量不为静音**（第 4 项要靠空气传播）
 *   - 系统已安装 Chrome（用 channel: chrome 直接驱动，不下载额外浏览器）
 */
import { createInterface } from 'node:readline'
import { writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { chromium } from 'playwright-core'

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..')

/**
 * 离开 standby 后可能出现的状态集合（第 3 项判据用）。
 *
 * 刻意不写死 `awaiting_answer`：用户说完唤醒词后常常**顺口把答案也说了**，状态会一路
 * 走到 thinking/responding。写死单一目标会把这种「答得比预期多」误判为失败。
 *
 * The set of states reachable after leaving standby (check 3's verdict). Deliberately not
 * pinned to `awaiting_answer`: users often say the answer right after the wake word, and the
 * state then runs on to thinking/responding. Pinning it would misjudge "answered more than
 * expected" as a failure.
 */
const LEFT_STANDBY_STATES = [
  'awaiting_answer', 'recording', 'transcribing', 'thinking',
  'tool_calling', 'responding', 'done', 'error',
]

/** 命令行参数解析。Command-line argument parsing. */
function parseArgs(argv) {
  const out = { url: 'http://127.0.0.1:8520', skip: [], report: '', headless: false }
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a === '--url') out.url = argv[++i]
    else if (a === '--skip') out.skip = argv[++i].split(',').map(s => s.trim())
    else if (a === '--report') out.report = argv[++i]
    else if (a === '--headless') out.headless = true
  }
  return out
}

const ARGS = parseArgs(process.argv.slice(2))
const rl = createInterface({ input: process.stdin, output: process.stdout })

/** 打印一行。Print a line. */
const say = (...a) => console.log(...a)
/** 睡 ms 毫秒。Sleep for the given milliseconds. */
const sleep = ms => new Promise(r => setTimeout(r, ms))
/** 等待用户回车。Wait for the user to press Enter. */
const enter = q => new Promise(r => rl.question(q, r))

/**
 * 带倒计时的等待，期间持续打印剩余秒数。
 * Wait with a live countdown, printing the remaining seconds.
 *
 * @param {number} seconds 等待秒数。Number of seconds to wait.
 * @param {string} label 提示前缀。Prompt prefix.
 */
async function countdown(seconds, label) {
  for (let s = seconds; s > 0; s--) {
    process.stdout.write(`\r  ${label} ${s}s …   `)
    await sleep(1000)
  }
  process.stdout.write('\r' + ' '.repeat(60) + '\r')
}

// ─────────────────────────── 采样与状态读取 / Sampling ───────────────────────────

/**
 * 浏览器侧的探针：每 150ms 采一次「状态机 / 唤醒引擎 / 真实播报」三元组。
 *
 * 三个信号来自三个互相独立的地方，这正是判据可信的原因：
 * - `state`：`.ball-status-ring` 的状态类，前端状态机的**结果**（用户看到的）
 * - `isRunning`：`window.WakeWordEngine.isRunning()`，唤醒引擎的**实际**运行状态
 * - `speaking`：`speechSynthesis.speaking`，浏览器的**真实**播报标志（与 App 无关）
 *
 * Browser-side probe sampling the (state machine / wake engine / real playback) triple every
 * 150ms. The three signals come from three independent places, which is what makes the
 * verdicts trustworthy: the DOM state class is the state machine's *result*, `isRunning` is
 * the engine's *actual* state, and `speechSynthesis.speaking` is the browser's *real*
 * playback flag independent of the app.
 */
const PROBE = () => {
  const ring = document.querySelector('.ball-status-ring')
  return {
    t: Date.now(),
    state: ring ? (ring.classList[1] || '') : '',
    isRunning: !!(window.WakeWordEngine && window.WakeWordEngine.isRunning && window.WakeWordEngine.isRunning()),
    speaking: !!(window.speechSynthesis && window.speechSynthesis.speaking),
  }
}

/**
 * 启动一个周期性采样器。
 * Start a periodic sampler.
 *
 * @param {import('playwright-core').Page} page 页面。The page.
 * @returns {{samples: object[], stop: () => void, states: () => string[]}} 采样器句柄。The sampler handle.
 */
function startSampler(page) {
  const samples = []
  const timer = setInterval(async () => {
    try { samples.push(await page.evaluate(PROBE)) } catch { /* 页面导航中，忽略一次采样 */ }
  }, 150)
  return {
    samples,
    stop: () => clearInterval(timer),
    /** 去重后的状态序列（保序）。The de-duplicated state sequence, order preserved. */
    states: () => samples.reduce((acc, s) => (acc.at(-1) === s.state || !s.state) ? acc : [...acc, s.state], []),
  }
}

/** 读一次当前状态。Read the current state once. */
const getState = page => page.evaluate(PROBE).then(p => p.state)

/**
 * 阻塞直到状态变为目标值之一，或超时。
 * Block until the state becomes one of the targets, or the timeout elapses.
 *
 * @param {import('playwright-core').Page} page 页面。The page.
 * @param {string[]} targets 目标状态。Target states.
 * @param {number} timeoutMs 超时毫秒。Timeout in milliseconds.
 * @returns {Promise<{ok: boolean, state: string, ms: number}>} 结果与耗时。Result and elapsed ms.
 */
async function waitForState(page, targets, timeoutMs) {
  const t0 = Date.now()
  while (Date.now() - t0 < timeoutMs) {
    const s = await getState(page)
    if (targets.includes(s)) return { ok: true, state: s, ms: Date.now() - t0 }
    await sleep(150)
  }
  return { ok: false, state: await getState(page), ms: Date.now() - t0 }
}

// ─────────────────────────── 场景搭建 / Scenario setup ───────────────────────────

/**
 * 记录网络请求（带时间戳），供「有没有发某个请求」这类判据使用。
 * Record network requests with timestamps, for "was this request issued" verdicts.
 *
 * @param {import('playwright-core').Page} page 页面。The page.
 * @returns {{list: object[], since: (t: number, re: RegExp) => object[]}} 请求记录器。The request log.
 */
function trackRequests(page) {
  const list = []
  page.on('request', r => {
    const u = new URL(r.url())
    // 记下请求体：报告里能看到「答案原文是什么」「utter 带的是哪套 messages」，
    // 排查时比只有路径有用得多。
    // Keep the request body: the report can then show what the answer actually was and which
    // messages the utter carried — far more useful when diagnosing than a bare path.
    let body = r.postData() || ''
    if (body.length > 300) body = body.slice(0, 300) + '…'
    if (u.pathname.startsWith('/api/')) {
      list.push({ t: Date.now(), method: r.method(), path: u.pathname, body })
    }
  })
  return { list, since: (t, re) => list.filter(r => r.t >= t && re.test(r.path)) }
}

/**
 * 确保语音唤醒引擎已启动。
 * Make sure the voice wake engine is running.
 *
 * @param {import('playwright-core').Page} page 页面。The page.
 * @param {number} timeoutMs 等待毫秒。Timeout in milliseconds.
 * @returns {Promise<boolean>} 是否已进入 listening。Whether it reached listening.
 */
async function ensureWake(page, timeoutMs = 25000) {
  if ((await getState(page)) === 'listening') return true
  // 面板未展开时用页面上的文字按钮；展开后语音开关是球上的 mic 徽章。
  // With the panel closed use the page's text button; once expanded the voice toggle is the
  // mic badge on the ball.
  for (const sel of ['text=开启语音唤醒', '.ball-mic']) {
    try {
      const loc = page.locator(sel).first()
      if (await loc.count()) await loc.click({ timeout: 3000 })
    } catch { /* 选择器不适用，试下一个 */ }
    if ((await waitForState(page, ['listening'], 12000)).ok) return true
  }
  return (await waitForState(page, ['listening'], timeoutMs)).ok
}

/**
 * 确保悬浮球面板已展开（发消息需要里面的输入框）。
 * Make sure the floating panel is expanded (sending a message needs its input).
 *
 * @param {import('playwright-core').Page} page 页面。The page.
 */
async function ensurePanel(page) {
  if (await page.locator('textarea').count()) return
  await page.locator('.float-trigger').click()
  await page.waitForSelector('textarea', { timeout: 10000 })
}

/**
 * 确保「播报」开关打开 —— 关着的话第 4 项没有声音可测，整个验收会变成空转。
 * Make sure the speak toggle is on: with it off there is no audio for check 4 and the whole
 * run silently degenerates.
 *
 * @param {import('playwright-core').Page} page 页面。The page.
 * @returns {Promise<boolean>} 播报是否开启。Whether playback is enabled.
 */
async function ensureSpeakOn(page) {
  const off = page.locator('.tm-toggle', { hasText: '播报' }).locator('.ui-toggle:not(.on)')
  if (await off.count()) {
    await off.first().click()
    await sleep(300)
  }
  return (await page.locator('.tm-toggle', { hasText: '播报' }).locator('.ui-toggle.on').count()) > 0
}

/**
 * 把一条消息发进助手（填输入框 + 点发送）。
 * Send one message to the assistant (fill the input, click send).
 *
 * @param {import('playwright-core').Page} page 页面。The page.
 * @param {string} text 消息文本。The message text.
 */
async function sendMessage(page, text) {
  await ensurePanel(page)
  await page.locator('textarea').first().fill(text)
  await page.locator('.ci-send').first().click()
}

/**
 * 发一条消息并等它触发一个待答提问（播报已结束 → 已开录）。
 *
 * Send a message and wait for it to produce a pending question (playback finished, recording
 * has begun).
 *
 * @param {import('playwright-core').Page} page 页面。The page.
 * @param {string} text 消息文本。The message text.
 * @param {number} timeoutMs 超时毫秒。Timeout in milliseconds.
 * @returns {Promise<{ok: boolean, question: string}>} 是否就绪与问题文本。Readiness and the question text.
 */
async function newScenario(page, text, timeoutMs = 90000) {
  await sendMessage(page, text)
  const r = await waitForState(page, ['awaiting_answer'], timeoutMs)
  return { ok: r.ok, question: r.ok ? await readPendingQuestion(page) : '' }
}

/**
 * 读取当前待答问题的文本（用于报告与人工核对）。
 * Read the text of the pending question (for the report and for human cross-checking).
 *
 * @param {import('playwright-core').Page} page 页面。The page.
 * @returns {Promise<string>} 问题文本。The question text.
 */
async function readPendingQuestion(page) {
  return page.evaluate(() => {
    const el = document.querySelector('.qq-q, .mini-bubble.ai, .float-panel')
    return (el?.innerText || '').split('\n').filter(Boolean).slice(-4).join(' / ').slice(0, 200)
  })
}

// ─────────────────────────── 报告 / Reporting ───────────────────────────

const results = []

/**
 * 记录一项验收结果。
 * Record one acceptance result.
 *
 * @param {string} id 编号。The item id.
 * @param {string} title 标题。The title.
 * @param {'PASS'|'FAIL'|'INCONCLUSIVE'|'SKIP'} status 结论。The verdict.
 * @param {string} detail 说明。The explanation.
 * @param {string} evidence 证据。The evidence.
 */
function record(id, title, status, detail, evidence = '') {
  results.push({ id, title, status, detail, evidence })
  const mark = { PASS: '✅', FAIL: '❌', INCONCLUSIVE: '⚠️ ', SKIP: '⏭️ ' }[status]
  say(`\n${mark} 第 ${id} 项 ${status}：${title}`)
  say(`   ${detail}`)
  if (evidence) say(`   证据：${evidence}`)
}

/** 生成 markdown 报告。Build the markdown report. */
function buildReport(meta) {
  const lines = [
    '# 语音验收报告（P6 / 子系统 C）',
    '',
    `> 由 \`web/scripts/verify-voice.mjs\` 自动生成于 ${new Date().toLocaleString('zh-CN')}`,
    `> 应用地址：${meta.url}　唤醒词：${meta.keyword}　待答超时：${meta.answerTimeout}ms　播报开关：${meta.speakOn ? '开' : '**关**'}`,
    '',
    '| # | 验收项 | 结论 | 说明 |',
    '|---|--------|------|------|',
    ...results.map(r => `| ${r.id} | ${r.title} | ${r.status} | ${r.detail} |`),
    '',
  ]
  const withEvidence = results.filter(r => r.evidence)
  if (withEvidence.length) {
    lines.push('## 证据明细', '')
    for (const r of withEvidence) {
      lines.push(`### 第 ${r.id} 项 · ${r.title}`, '', '```', r.evidence, '```', '')
    }
  }
  lines.push(
    '## 结论口径', '',
    '- `PASS` 仅表示**本次运行**采集到的客观证据符合预期，不代表任意环境都成立。',
    '- `INCONCLUSIVE` 表示场景没搭成（如助手没念出唤醒词），**不是通过**。',
    '- 未跑到的项标 `SKIP`。',
    '',
  )
  return lines.join('\n')
}

// ─────────────────────────── 主流程 / Main ───────────────────────────

async function main() {
  say('═'.repeat(72))
  say(' 语音验收台 · P6 语音作答 / 待机 / 再唤醒续答 / 播报期不自触发')
  say('═'.repeat(72))
  say(`应用地址：${ARGS.url}`)
  say('前置检查：后端已启动；麦克风与扬声器可用且未静音；系统已装 Chrome。')
  say('')
  await enter('准备好后按回车开始（将打开一个 Chrome 窗口）… ')

  let browser
  try {
    browser = await chromium.launch({
      channel: 'chrome',
      headless: ARGS.headless,
      args: [
        // 自动同意麦克风授权弹窗（注意：只自动同意，**不**伪造音频设备 ——
        // 这几项验收要的正是真人对着真麦克风说话）。
        // Auto-accept the mic permission dialog. Note: this only auto-accepts; it does NOT
        // fake the audio device — these checks specifically need a real human on a real mic.
        '--use-fake-ui-for-media-stream',
        '--autoplay-policy=no-user-gesture-required',
      ],
    })
  } catch (e) {
    say('\n❌ 无法启动 Chrome：' + e.message)
    say('   请确认已安装 Google Chrome；或改用 Edge：把 verify-voice.mjs 里的 channel 改为 "msedge"。')
    rl.close()
    process.exitCode = 2
    return
  }

  const ctx = await browser.newContext({ permissions: ['microphone'] })
  const page = await ctx.newPage()

  // 记录浏览器控制台报错，报告里附上，便于发现隐藏异常。
  // Collect console errors to attach to the report so hidden faults surface.
  const consoleErrors = []
  page.on('console', m => { if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 200)) })

  const reqs = trackRequests(page)

  await page.goto(ARGS.url, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(2500)

  // 配置：待答超时是第 2 项的判据基准，唤醒词是第 3/4 项的依据。
  // Config: the answer timeout is check 2's baseline; the wake keyword underpins checks 3/4.
  const cfg = await page.evaluate(async () => (await fetch('/api/config')).json()).catch(() => ({}))
  const answerTimeout = cfg?.vad?.answer_timeout_ms ?? 8000
  const keyword = cfg?.wake_word?.keyword ?? '小逻小逻'

  await ensurePanel(page)
  const speakOn = await ensureSpeakOn(page)
  if (!speakOn) {
    say('\n⚠️  「播报」开关处于关闭状态，第 4 项将没有音频可测（会标 INCONCLUSIVE）。')
  }

  if (!(await ensureWake(page))) {
    say('\n❌ 语音唤醒引擎未能在 25s 内进入 listening。')
    say('   常见原因：Vosk 模型未加载（看 .playwright-mcp 或浏览器控制台）、麦克风被占用。')
    say('   后续 4 项全部标 SKIP。')
    for (const [id, t] of [['1', '播报结束后直接开口说答案'], ['2', '播报后沉默 → 待机'],
                           ['3', '待机态唤醒 → 续答本题'], ['4', '播报含唤醒词 → 不自触发']]) {
      record(id, t, 'SKIP', '唤醒引擎未启动，场景无法搭建')
    }
  } else {
    say('\n✓ 唤醒引擎已启动（state = listening）')
    await runChecks({ page, reqs, keyword, answerTimeout, speakOn })
  }

  await browser.close()
  rl.close()

  const report = buildReport({ url: ARGS.url, keyword, answerTimeout, speakOn })
  const reportPath = ARGS.report || resolve(REPO_ROOT, 'docs', 'superpowers', 'plans', 'voice-verification-report.md')
  writeFileSync(reportPath, report, 'utf-8')

  say('\n' + '═'.repeat(72))
  const pass = results.filter(r => r.status === 'PASS').length
  const fail = results.filter(r => r.status === 'FAIL').length
  const inc = results.filter(r => r.status === 'INCONCLUSIVE').length
  const skip = results.filter(r => r.status === 'SKIP').length
  say(` 汇总：PASS ${pass}　FAIL ${fail}　INCONCLUSIVE ${inc}　SKIP ${skip}`)
  say(` 报告已写入：${reportPath}`)
  if (consoleErrors.length) say(` 浏览器控制台报错 ${consoleErrors.length} 条（见报告）`)
  say('═'.repeat(72))
  say('')
  say('把报告粘进 docs/superpowers/plans/2026-09-13-voice-answering.md 的验证记录，')
  say('并把其中「未验证」表里的对应行改为本报告的实际结论。')

  // 有 FAIL 时以非零退出码结束，便于脚本化调用。
  // Exit non-zero on any FAIL so this can gate a scripted run.
  if (fail > 0) process.exitCode = 1
}

/**
 * 依次跑完 4 项验收。
 * Run all 4 acceptance checks in order.
 *
 * 顺序不是随意的：第 1 项用掉一个提问；第 2、3 项共用同一个提问（沉默 → 待机 → 唤醒续答
 * 本来就是一条连续的时间线）；第 4 项需要回到无待答提问的状态。
 *
 * The order is deliberate: check 1 consumes one question; checks 2 and 3 share a single
 * question (silence → standby → resume-on-wake is one continuous timeline by nature); check 4
 * needs to be back in a no-pending-question state.
 *
 * @param {{page: any, reqs: any, keyword: string, answerTimeout: number, speakOn: boolean}} ctx 上下文。Context.
 */
async function runChecks({ page, reqs, keyword, answerTimeout, speakOn }) {
  // ── 第 1 项：播报结束后直接开口说答案 ──
  if (ARGS.skip.includes('1')) {
    record('1', '播报结束后直接开口说答案', 'SKIP', '命令行指定跳过')
  } else {
    say('\n' + '─'.repeat(72))
    say('第 1 项：播报结束后直接开口说答案')
    say('─'.repeat(72))
    const sc = await newScenario(page, '帮我整理一下文件')
    if (!sc.ok) {
      record('1', '播报结束后直接开口说答案', 'FAIL',
        '发出消息后 90s 内没有进入 awaiting_answer（提问未产生或播报未结束）')
    } else {
      say(`\n助手提问：${sc.question}`)
      say('状态已到「请直接说出你的回答…」（= 播报结束、已开录）。')
      say(`\n👉 请现在对着麦克风说出问题的答案（随便说一句相关的即可，例如「下载目录」）。`)
      // 计时窗口必须**在用户开口之前**开始：用户是「先说、后按回车」，若把 t0 放在回车
      // 之后，请求早已发生，窗口内什么都采不到 —— 会把成功误判为失败。
      // The measurement window must open *before* the user speaks: they speak first and press
      // Enter afterwards, so starting t0 at the Enter would sample nothing and misjudge a
      // success as a failure.
      const t0 = Date.now()
      await enter('   说完后按回车开始判定… ')
      // 给它几分钟：真人说话 + ASR 往返 + 后端往返，比纯机器链路慢得多。
      // Allow minutes: a human speaking plus the ASR round-trip is far slower than a
      // machine-only path.
      const hit = await waitFor(() => reqs.since(t0, /^\/api\/voice\/answer$/), 120000)
      const after = await getState(page)
      record('1', '播报结束后直接开口说答案', hit ? 'PASS' : 'FAIL',
        hit ? `语音作答被识别并投递到 /api/voice/answer（${((hit.t - t0) / 1000).toFixed(1)}s）`
            : '120s 内没有收到 /api/voice/answer —— 语音没有被识别为本题答案',
        `按回车后状态：${after}\n` +
        `窗口内 /api/voice/* 请求：\n` +
        reqs.since(t0, /^\/api\/voice\//).map(r => `  ${r.method} ${r.path}  body=${r.body}`).join('\n'))
    }
  }

  // ── 第 2 项：播报后沉默 → 待机 ──
  if (ARGS.skip.includes('2')) {
    record('2', '播报后沉默 → 待机', 'SKIP', '命令行指定跳过')
  } else {
    say('\n' + '─'.repeat(72))
    say('第 2 项：播报后沉默 → 待机（本项全自动判定）')
    say('─'.repeat(72))
    const sc = await newScenario(page, '帮我整理一下下载文件夹')
    if (!sc.ok) {
      record('2', '播报后沉默 → 待机', 'FAIL',
        '发出消息后 90s 内没有进入 awaiting_answer，场景未搭成')
    } else {
      const sampler = startSampler(page)
      say(`\n助手提问：${sc.question}`)
      say(`\n👉 请**不要说话**，保持沉默 —— 等 ${answerTimeout}ms 待答超时后应自动进入待机。`)
      // 倒计时与状态轮询并发跑：让用户知道还要安静多久，而不是干等一个不动的终端。
      // Run the countdown concurrently with the state poll so the user knows how much longer
      // to stay quiet instead of staring at a frozen terminal.
      const [r] = await Promise.all([
        waitForState(page, ['standby'], answerTimeout + 15000),
        countdown(Math.round(answerTimeout / 1000), '请保持沉默，待答超时还剩'),
      ])
      sampler.stop()
      const uiHasStandby = await page.evaluate(() => document.body.innerText.includes('待机'))
      const delta = Math.round(r.ms)
      const seq = sampler.states()
      // 判据：进了 standby，且耗时落在超时值附近（早太多说明是别的原因进的，晚太多
      // 说明超时没按配置生效）。
      // Verdict: it entered standby and the elapsed time is near the configured timeout —
      // much earlier means something else drove it, much later means the timeout did not
      // take effect as configured.
      const closeEnough = delta >= answerTimeout - 3000 && delta <= answerTimeout + 8000
      // 没进待机时区分两种成因 —— 二者要采取的行动完全不同：
      // (a) 麦克风采到了声音（VAD 判定有人说话 → 录音 → 转写 → 当成回答提交）：环境不安静，
      //     换安静房间重跑即可，不是缺陷；
      // (b) 状态一直停在 awaiting_answer：待答超时没生效，那才是真要查的。
      // When standby is not reached, separate two causes that call for completely different
      // actions: (a) the mic picked up sound (VAD saw speech → record → transcribe → submitted
      // as an answer) — a noisy room, rerun somewhere quiet, not a defect; (b) the state never
      // left awaiting_answer — the answer timeout is not working, and that is worth digging into.
      const heardSound = seq.some(s => s === 'transcribing' || s === 'thinking' || s === 'recording')
      const why = r.ok
        ? ''
        : heardAnswerWait(seq)
          ? `麦克风采到了声音（${seq.join(' → ')}）—— 本项要求 ${answerTimeout}ms 内**真正静音**，请在安静环境重跑；这不是待机功能的缺陷`
          : `${answerTimeout + 15000}ms 内未进入 standby（当前 ${r.state}）—— 待答超时没有生效，需排查`
      const status = r.ok && closeEnough ? 'PASS' : 'FAIL'
      record('2', '播报后沉默 → 待机', status,
        r.ok
          ? `沉默 ${delta}ms 后进入 standby（配置 ${answerTimeout}ms）${closeEnough ? '' : ' — 耗时偏离配置超时值，请核对 vad.answer_timeout_ms 是否生效'}`
          : why,
        `状态序列：${seq.join(' → ')}\n界面出现「待机」文案：${uiHasStandby ? '是' : '否'}\n` +
        `采集到声音（VAD 触发录音）：${heardSound ? '是' : '否'}`)
    }
  }

  // ── 第 3 项：待机态唤醒 → 续答本题 ──
  if (ARGS.skip.includes('3')) {
    record('3', '待机态唤醒 → 续答本题', 'SKIP', '命令行指定跳过')
  } else {
    say('\n' + '─'.repeat(72))
    say('第 3 项：待机态唤醒 → 回到本题续答（而非开新一轮）')
    say('─'.repeat(72))
    const before = await getState(page)
    if (before !== 'standby') {
      record('3', '待机态唤醒 → 续答本题', 'INCONCLUSIVE',
        `前置状态应为 standby，实际为 ${before}（多半是第 2 项没进待机）—— 场景未搭成`)
    } else {
      say(`\n👉 请现在说出唤醒词「${keyword}」。`)
      say('   预期：回到**刚才那个提问**继续作答，而不是开始新一轮对话。')
      // 同第 1 项：窗口开在用户开口之前。
      // As in check 1: the window opens before the user speaks.
      const t0 = Date.now()
      await enter('   说完后按回车开始判定… ')
      // 判据：**离开了 standby** 且**没有新的 /api/voice/utter**。
      //
      // 后半句才是决定性的：走新一轮必然经过 runTurn → /voice/utter，而那条新请求会
      // abort 掉当前流，让后端阻塞中的 ask() 永久挂死 —— 正是本设计要修的老缺陷。
      // 所以「没有新 utter」这一条足以把「续答本题」和「开新一轮」分开。
      //
      // Verdict: it left standby AND no new /api/voice/utter. The second half is decisive: a
      // new round necessarily goes through runTurn → /voice/utter, and that new request aborts
      // the live stream, leaving the backend's blocked ask() hanging forever — the very defect
      // this design fixes. So "no new utter" alone separates resuming from starting over.
      const back = await waitForState(page, LEFT_STANDBY_STATES, 60000)
      const newUtters = reqs.since(t0, /^\/api\/voice\/utter$/)
      const leftStandby = back.ok
      const status = leftStandby && newUtters.length === 0 ? 'PASS' : 'FAIL'
      record('3', '待机态唤醒 → 续答本题', status,
        leftStandby && newUtters.length === 0
          ? `唤醒后离开 standby 回到 ${back.state}，且未发新的 /api/voice/utter（${(back.ms / 1000).toFixed(1)}s）—— 续答本题`
          : leftStandby
            ? `离开了 standby，但发出了 ${newUtters.length} 条新的 /api/voice/utter —— 走成了新一轮（正是要修的老缺陷）`
            : `唤醒后 60s 内没有离开 standby（当前 ${back.state}）—— 唤醒词没有被识别`,
        `唤醒后状态：${back.state}\n新 /api/voice/utter 条数：${newUtters.length}`)
    }
  }

  // ── 第 4 项：播报含唤醒词不自触发 ──
  if (ARGS.skip.includes('4')) {
    record('4', '播报含唤醒词 → 不自触发', 'SKIP', '命令行指定跳过')
  } else if (!speakOn) {
    record('4', '播报含唤醒词 → 不自触发', 'INCONCLUSIVE',
      '「播报」开关关闭，助手的播报不会出声，这项测不到（不是通过）')
  } else {
    say('\n' + '─'.repeat(72))
    say('第 4 项：助手播报含唤醒词的文本 → 不应自触发唤醒')
    say('─'.repeat(72))
    await runSelfTriggerCheck({ page, keyword, reqs })
  }
}

/**
 * 第 4 项的实现：让助手**用自己正常的播报链路**念出含唤醒词的文本，播报期间观察唤醒引擎。
 *
 * Implementation of check 4: have the assistant speak a wake-word-containing text through its
 * *own normal playback path* and watch the wake engine during playback.
 *
 * 关键点：必须走 App 自己的播报（它才会去设置 speaking 并触发门控）。直接注入
 * speechSynthesis.speak 绕过了门控，那样测的是浏览器而不是本功能 —— 假通过。
 *
 * The crux: it must go through the app's own playback (only that sets `speaking` and engages
 * the gate). Injecting speechSynthesis.speak directly bypasses the gate, which would test the
 * browser rather than this feature — a false pass.
 *
 * @param {{page: any, keyword: string, reqs: any}} ctx 上下文。Context.
 */
async function runSelfTriggerCheck({ page, keyword, reqs }) {
  // 挂钩 speechSynthesis.speak 以**记录实际播报出去的文本** —— 这是「场景是否真的搭成」
  // 的唯一可信依据（LLM 不一定老实复述）。
  // Hook speechSynthesis.speak to record the text actually broadcast — the only trustworthy
  // basis for "was the scenario really set up", since the LLM may not repeat verbatim.
  await page.evaluate(() => {
    window.__spoken = []
    if (!window.__speakHooked) {
      const orig = window.speechSynthesis.speak.bind(window.speechSynthesis)
      window.speechSynthesis.speak = u => { window.__spoken.push(u.text || ''); return orig(u) }
      window.__speakHooked = true
    }
  })

  let spoken = ''
  let sampler = null
  for (let attempt = 1; attempt <= 2 && !spoken.includes(keyword); attempt++) {
    say(`\n第 ${attempt} 次尝试让助手念出「${keyword}」…`)
    await page.evaluate(() => { window.__spoken = [] })

    // 采样必须在发消息**之前**启动 —— 门控动作发生在播报期间，播报一结束引擎就重启了，
    // 事后补采会看到「一切正常」的假象。
    // Sampling must start *before* the message: the gate acts during playback and the engine
    // restarts the moment it ends, so sampling afterwards would show a falsely clean picture.
    sampler = startSampler(page)
    await sendMessage(page, `请一字不差地念出下面这四个字，不要添加任何其他文字：${keyword}`)

    // 先等播报开始（__spoken 由上面的挂钩填充），再等播报结束。
    // First wait for playback to start (__spoken is filled by the hook above), then for it to
    // end.
    const began = await waitFor(() => page.evaluate(() => (window.__spoken || []).length), 90000)
    if (began) await waitPlaybackEnd(page, 60000)
    sampler.stop()

    spoken = (await page.evaluate(() => (window.__spoken || []).join(' | '))).slice(0, 400)
    say(`  实际播报文本：${spoken ? spoken.slice(0, 120) : '(无)'}`)
  }

  if (!spoken.includes(keyword)) {
    record('4', '播报含唤醒词 → 不自触发', 'INCONCLUSIVE',
      `助手两次都没有念出「${keyword}」，播报里没有唤醒词就测不到自触发 —— 不是通过`,
      `实际播报文本：${spoken || '(空)'}`)
    return
  }

  // 分析播报期间的采样。判据两条，缺一不可：
  // 1) 门控**确实生效**：播报期内唤醒引擎被停过（isRunning 出现 false）
  // 2) **确实没自触发**：全程没有任何一次进入 recording（进 recording 就意味着引擎听见
  //    了唤醒词并开了录）
  //
  // Analyse the samples taken during playback. Two necessary conditions: the gate really
  // engaged (isRunning went false at some point during playback) and nothing self-triggered
  // (the state never once became recording — entering recording means the engine heard the
  // wake word and opened the mic).
  const samples = sampler?.samples ?? []
  const playback = samples.filter(s => s.speaking)
  const stoppedDuring = playback.filter(s => !s.isRunning)
  const recording = samples.filter(s => s.state === 'recording')
  const stateSeq = samples.reduce((a, s) => (a.at(-1) === s.state || !s.state ? a : [...a, s.state]), [])
  // 播报前后各有多少采样里引擎在跑 —— 用来证明「播报期引擎停着」不是因为引擎压根没起来。
  // 若前后都在跑、只有播报期不跑，才是门控真的生效。
  // How many samples had the engine running before and after playback — proof that "stopped
  // during playback" is not simply the engine never having started. Running before and after
  // but not during is what makes it the gate.
  const firstPlayIdx = samples.findIndex(s => s.speaking)
  const before = samples.slice(0, firstPlayIdx < 0 ? 0 : firstPlayIdx)
  const after = samples.slice(firstPlayIdx < 0 ? samples.length : samples.findLastIndex(s => s.speaking) + 1)
  const runningBefore = before.filter(s => s.isRunning).length
  const runningAfter = after.filter(s => s.isRunning).length

  let status, detail
  if (!playback.length) {
    status = 'INCONCLUSIVE'
    detail = '本次采样没有捕捉到 speechSynthesis 播报窗口，无法判定（不是通过）'
  } else if (recording.length) {
    status = 'FAIL'
    detail = `播报期间状态机进入过 recording —— 助手自己的声音触发了唤醒（${recording.length} 次采样）`
  } else if (!stoppedDuring.length) {
    status = 'FAIL'
    detail = '播报期间唤醒引擎始终在运行 —— 门控没有生效，只是这次恰好没被触发'
  } else {
    status = 'PASS'
    detail = `播报期间唤醒引擎被暂停（${stoppedDuring.length}/${playback.length} 次采样未运行），且全程未进入 recording`
  }

  record('4', '播报含唤醒词 → 不自触发', status, detail,
    `播报文本：${spoken.slice(0, 160)}\n` +
    `引擎运行采样数 —— 播报前 ${runningBefore}/${before.length}，播报期 ${playback.length - stoppedDuring.length}/${playback.length}，播报后 ${runningAfter}/${after.length}\n` +
    `（播报前后都在跑、只有播报期不跑 = 门控确实生效；若播报期也在跑则判 FAIL）\n` +
    `进入 recording 的采样数：${recording.length}\n` +
    `状态序列：${stateSeq.join(' → ')}\n` +
    `注：本项可证伪的部分是**门控本身**。声学上的自触发还取决于扬声器→麦克风的实际通路；\n` +
    `    若扬声器静音或麦克风听不到扬声器，第二半句无判别力（但第一半句仍有效）。`)
}

/**
 * 状态序列里是否出现「麦克风采到声音」的迹象。
 *
 * 待答期间 VAD 一旦判定有人说话就会录音 → 转写 → 当成回答提交，于是永远等不到待答超时。
 * 这三个状态是那条路径的指纹。
 *
 * Whether the state sequence shows the mic picked up sound. During the answer wait, VAD
 * judging speech present starts a recording → transcription → submitted as an answer, so the
 * answer timeout is never reached. These three states are that path's fingerprint.
 *
 * @param {string[]} seq 状态序列。The state sequence.
 * @returns {boolean} 是否采到了声音。Whether sound was picked up.
 */
function heardAnswerWait(seq) {
  return seq.some(s => s === 'recording' || s === 'transcribing' || s === 'thinking')
}

/**
 * 等播报结束（speechSynthesis.speaking 由真转假）。
 * Wait for playback to end (speechSynthesis.speaking going from true to false).
 *
 * @param {import('playwright-core').Page} page 页面。The page.
 * @param {number} timeoutMs 超时毫秒。Timeout in milliseconds.
 */
async function waitPlaybackEnd(page, timeoutMs) {
  const t0 = Date.now()
  while (Date.now() - t0 < timeoutMs) {
    const on = await page.evaluate(() => !!window.speechSynthesis?.speaking)
    if (!on) return
    await sleep(200)
  }
}

/**
 * 轮询等待条件成立。
 * Poll until the predicate yields a truthy value.
 *
 * 必须 `await fn()` —— 谓词常是 `page.evaluate(...)`（返回 Promise，恒为真），不 await 的话
 * 第一次轮询就会把 Promise 本身当成结果返回，条件等于没判。
 *
 * Must `await fn()`: predicates are often `page.evaluate(...)`, which returns an always-truthy
 * Promise; without awaiting, the very first poll would return that Promise as the result and
 * the condition would never actually be tested.
 *
 * @param {() => any} fn 条件函数。The predicate.
 * @param {number} timeoutMs 超时毫秒。Timeout in milliseconds.
 * @returns {Promise<any>} 条件返回的真值（数组则取其首项），或 null。The truthy value (first item for arrays), or null.
 */
async function waitFor(fn, timeoutMs) {
  const t0 = Date.now()
  while (Date.now() - t0 < timeoutMs) {
    const v = await fn()
    if (v && (!Array.isArray(v) || v.length)) return Array.isArray(v) ? v[0] : v
    await sleep(200)
  }
  return null
}

main().catch(e => {
  console.error('\n验收台异常终止：', e)
  try { rl.close() } catch { /* 已关闭 */ }
  process.exitCode = 3
})
