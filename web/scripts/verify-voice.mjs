#!/usr/bin/env node
/**
 * 语音验收台 — 「播报后语音作答 / 待答说唤醒词即弃题开新轮 / 播报期不自触发 /
 * 通话免唤醒」4 条人工验收项的自动化辅助。
 *
 * Voice acceptance harness — an automated assistant for the 4 manual acceptance items
 * (voice answering / wake-abandon during the answer wait / no self-trigger while
 * speaking / wake-free call mode).
 *
 * 为什么需要它：这几项都需要真人对着麦克风说话、用耳朵听播报，无法用 Vitest 替代
 * （真实的麦克风/扬声器通路驱动不了）。但「谁对谁错」的**判据**大部分是客观的
 * —— 弃题 stop 发没发、唤醒词有没有被误当答案提交（/voice/answer）、播报期间有没有
 * 任何音频分段被上传 —— 这些可以自动采集。于是本脚本负责搭场景、采证据、判客观项，
 * 人只负责出声和听声。
 *
 * 判据的来源：**采不到证据就报 INCONCLUSIVE，绝不报 PASS**。这条比任何单项检查都重要 ——
 * 一个「什么都没看见所以通过」的检查是假保障，比没有检查更糟。
 *
 * Why this exists: these items need a human at the microphone and ears on the speaker and
 * cannot be replaced by Vitest (a real mic/speaker path cannot be driven). But most of the
 * *verdicts* are objective — was the abandon stop issued, was the wake word mistakenly
 * submitted as an answer (/voice/answer), was any audio segment uploaded during playback —
 * and those can be captured automatically. So the harness builds the scenario, collects
 * the evidence and decides the objective parts; the human only has to make sound and listen.
 *
 * Where the verdicts come from: **no evidence means INCONCLUSIVE, never PASS**. That rule
 * outranks every individual check — a check that passes because it saw nothing is a false
 * assurance, worse than having no check at all.
 *
 * 用法 / Usage:
 *   cd web && npm run verify:voice                  # 默认 http://127.0.0.1:8520
 *   npm run verify:voice -- --url http://127.0.0.1:5173
 *   npm run verify:voice -- --skip 3                # 跳过播报自触发项
 *   npm run verify:voice -- --skip 4                # 跳过通话模式项
 *
 * 前置 / Prerequisites:
 *   - 后端已启动且前端已构建（python main.py serve），或 vite dev server 在跑
 *   - 本机有可用麦克风与扬声器，且**音量不为静音**（第 3 项的声学部分要靠空气传播）
 *   - 系统已安装 Chrome（用 channel: chrome 直接驱动，不下载额外浏览器）
 */
import { createInterface } from 'node:readline'
import { writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { chromium } from 'playwright-core'

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..')

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
 * 安装麦克风探针：记录 `getUserMedia` 取到的音频轨道与 `track.stop()` 的释放，
 * 由此可以读出**某一时刻还有几条活着的麦克风轨道**。
 *
 * 为什么需要它：新架构里「播报期不自触发」靠的是**播报期间麦克风真的被关掉**（useWakeWord
 * 的 speaking watcher 调 stopListening → 停轨道）。只断言「播报期没有上传」是不够的 ——
 * 上传是**结果**，麦克风是否还开着是**原因**；必须确认原因，判据才不空洞。
 * 旧版探 `window.WakeWordEngine.isRunning()`：该全局已随 Vosk 一起删除，取值恒为假，
 * FAIL 分支永不触发 —— 一个「什么都没看见所以通过」的假保障，正是本次要修的东西。
 *
 * Install the microphone probe: record the audio tracks `getUserMedia` hands out and the
 * `track.stop()` releases, so the number of **live mic tracks** at any instant can be read.
 *
 * Why it is needed: in the new architecture "no self-trigger during playback" rests on the mic
 * genuinely being released while the assistant speaks (useWakeWord's speaking watcher calls
 * stopListening → stops the tracks). Asserting only "no upload happened" is not enough — the
 * upload is the *effect* and the open mic is the *cause*; confirming the cause is what keeps the
 * verdict from being vacuous. The old probe read `window.WakeWordEngine.isRunning()`, a global
 * deleted along with Vosk, so it was permanently falsy and its FAIL branch was unreachable — a
 * false assurance of exactly the kind this rework exists to remove.
 *
 * @param {import('playwright-core').Page} page 页面。The page.
 * @returns {Promise<boolean>} 探针是否可用。Whether the probe is available.
 */
async function installMicProbe(page) {
  return page.evaluate(() => {
    if (window.__micProbe) return true
    try {
      const md = navigator.mediaDevices
      if (!md || typeof md.getUserMedia !== 'function' || typeof MediaStreamTrack === 'undefined') return false
      const log = { acquires: [], stops: [] }
      const origGum = md.getUserMedia.bind(md)
      // 挂在实例上遮蔽原型方法：App 读 navigator.mediaDevices.getUserMedia 就会拿到这一层。
      // Own property shadowing the prototype method, so the app's read of
      // navigator.mediaDevices.getUserMedia hits this wrapper.
      md.getUserMedia = async (constraints) => {
        const stream = await origGum(constraints)
        log.acquires.push({ t: Date.now(), tracks: stream.getAudioTracks().length })
        return stream
      }
      const origStop = MediaStreamTrack.prototype.stop
      MediaStreamTrack.prototype.stop = function () {
        if (this.kind === 'audio') log.stops.push(Date.now())
        return origStop.call(this)
      }
      window.__micProbe = log
      return true
    } catch { return false }
  })
}

/**
 * 浏览器侧的探针：每 150ms 采一次「状态机 / 麦克风活轨道 / 真实播报」三元组。
 *
 * 三个信号来自三个互相独立的地方，这正是判据可信的原因：
 * - `state`：`.ball-status-ring` 的状态类，前端状态机的**结果**（用户看到的）
 * - `micLive`：活着的音频轨道数（见 installMicProbe），麦克风的**实际**开合状态
 * - `speaking`：`speechSynthesis.speaking`，浏览器的**真实**播报标志（与 App 无关）
 *
 * `micLive` 为 `null` 表示探针不可用 —— 判据据此报 INCONCLUSIVE，而不是把 null 当成 0
 * （把「测不到」当成「没开着」正是假保障的成因）。
 *
 * Browser-side probe sampling the (state machine / live mic tracks / real playback) triple every
 * 150ms. The three signals come from three independent places, which is what makes the verdicts
 * trustworthy: the DOM state class is the state machine's *result*, `micLive` is the mic's
 * *actual* open/closed state (see installMicProbe), and `speechSynthesis.speaking` is the
 * browser's *real* playback flag independent of the app.
 *
 * `micLive === null` means the probe is unavailable — the verdict is then INCONCLUSIVE rather
 * than treating null as 0 (reading "cannot measure" as "not open" is how false assurances start).
 */
const PROBE = () => {
  const ring = document.querySelector('.ball-status-ring')
  const mic = window.__micProbe
  // 活轨道数按**轨道**记账（不是按取流次数）：一次取流可能带多条音频轨道，
  // 按次数记账会把 2 轨的流算成 1，凭空多出「已释放」的假象。
  // Live tracks are counted per *track*, not per acquisition: one acquisition can carry several
  // audio tracks, and counting acquisitions would under-report a 2-track stream as 1 — inventing
  // a release that never happened.
  const acquired = mic ? mic.acquires.reduce((n, a) => n + a.tracks, 0) : 0
  return {
    t: Date.now(),
    state: ring ? (ring.classList[1] || '') : '',
    micLive: mic ? Math.max(0, acquired - mic.stops.length) : null,
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
  // 语音开关只有一处：悬浮球上的 mic 徽章（`.ball-mic.on` = 已开启）。徽章是**切换**语义，
  // 所以只有确认它当前是关的才点 —— 否则会把已开启的唤醒点掉，后面 4 项全部变成空转。
  // There is exactly one voice toggle: the mic badge on the float ball (`.ball-mic.on` = enabled).
  // The badge *toggles*, so only click when it is currently off — clicking an enabled one would
  // switch wake off and silently degenerate all four checks.
  const badge = page.locator('.ball-mic').first()
  try {
    if (await badge.count() && !(await badge.evaluate(el => el.classList.contains('on')))) {
      await badge.click({ timeout: 3000 })
    }
  } catch { /* 徽章点不动，交给下面的状态轮询报错 */ }
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
 * 确保「播报」开关打开 —— 关着的话第 3 项没有声音可测，整个验收会变成空转。
 * Make sure the speak toggle is on: with it off there is no audio for check 3 and the whole
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
    `> 应用地址：${meta.url}　唤醒词：${meta.keyword}　播报开关：${meta.speakOn ? '开' : '**关**'}`,
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
  say(' 语音验收台 · 播报后作答 / 待答弃题开新轮 / 播报期不自触发 / 通话免唤醒')
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

  // 麦克风探针必须在**应用取流之前**装好（开启唤醒才会 getUserMedia，此刻还没开）。
  // 装不上不终止验收，但要如实告诉用户第 3 项将因此只能报 INCONCLUSIVE。
  // The mic probe must be installed *before* the app acquires a stream (only the wake enable
  // calls getUserMedia, and it has not happened yet). A failure does not abort the run, but the
  // user is told that check 3 can then only report INCONCLUSIVE.
  const micProbeOk = await installMicProbe(page)
  if (!micProbeOk) {
    say('\n⚠️  麦克风探针安装失败（页面里没有可用的 mediaDevices/MediaStreamTrack）。')
    say('   第 3 项无法证明「播报期麦克风确实关着」，将报 INCONCLUSIVE 而不是 PASS。')
  }

  // 配置：唤醒词是第 2/3 项的判据依据（弃题判定 + 让助手复述）。
  // Config: the wake keyword underpins checks 2 and 3 (abandon detection + verbatim repeat).
  const cfg = await page.evaluate(async () => (await fetch('/api/config')).json()).catch(() => ({}))
  // 唤醒词：/api/config 暴露的是**列表** `keywords`（单数 `keyword` 是 Vosk 时代的遗留字段，
  // 早已不在响应里）。原先读 `.keyword` 会静默落到兜底值「小逻小逻」—— 那是个**已废弃、
  // 根本唤不醒**的词，于是脚本会让操作者对着空气喊，检查 2/3 必然失败（而且是假失败）。
  // 兜底值必须是**当前真的能唤醒**的词；取列表首项即可 —— 检查 3 要让助手把它一字不差念出来，
  // 单项比多项更可靠。
  // Wake words: /api/config exposes the **list** `keywords` (the singular `keyword` is a Vosk-era
  // leftover long gone from the response). Reading `.keyword` silently fell back to 「小逻小逻」 —
  // a retired word that wakes nothing, so the harness would tell the operator to say a dead phrase
  // and checks 2/3 would fail for a bogus reason. The fallback must be a word that actually wakes.
  // Taking the first entry is enough: check 3 asks the assistant to repeat it verbatim, and one
  // word is more reliably repeated than several.
  const keyword = (cfg?.wake_word?.keywords ?? [])[0] ?? '衍衡'

  await ensurePanel(page)
  const speakOn = await ensureSpeakOn(page)
  if (!speakOn) {
    say('\n⚠️  「播报」开关处于关闭状态，第 3 项将没有音频可测（会标 INCONCLUSIVE）。')
  }

  if (!(await ensureWake(page))) {
    say('\n❌ 语音唤醒未能在 25s 内进入 listening。')
    say('   常见原因：麦克风被占用 / 权限被拒（看浏览器控制台与球上的状态行文案）、后端未启动。')
    say('   后续 4 项全部标 SKIP。')
    for (const [id, t] of [['1', '播报结束后直接开口说答案'], ['2', '待答说唤醒词 → 弃题开新轮'],
                           ['3', '播报含唤醒词 → 不自触发'], ['4', '通话模式免唤醒指令']]) {
      record(id, t, 'SKIP', '唤醒引擎未启动，场景无法搭建')
    }
  } else {
    say('\n✓ 唤醒引擎已启动（state = listening）')
    await runChecks({ page, reqs, keyword, speakOn })
    await runCallCheck(page, reqs)
  }

  await browser.close()
  rl.close()

  const report = buildReport({ url: ARGS.url, keyword, speakOn })
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
 * 依次跑完 3 项验收（通话模式在 runCallCheck 单独跑，是第 4 项）。
 * Run the 3 in-page acceptance checks in order (the call-mode check follows as item 4).
 *
 * 顺序不是随意的：第 1 项用掉一个提问（作答后回合自行跑完）；第 2 项自建一个待答提问、
 * 当场弃题开新轮（新轮用直答型指令，跑完不留待答提问）；第 3 项要求回到无待答提问的状态。
 *
 * The order is deliberate: check 1 consumes one question (its round finishes on its own);
 * check 2 builds its own pending question and abandons it into a new round on the spot (the
 * replacement command is a direct-answer type, so no pending question remains); check 3 needs
 * to be back in a no-pending-question state.
 *
 * @param {{page: any, reqs: any, keyword: string, speakOn: boolean}} ctx 上下文。Context.
 */
async function runChecks({ page, reqs, keyword, speakOn }) {
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

  // ── 第 2 项：待答期间说唤醒词 → 弃题开新轮 ──
  //
  // 取消限时回答后的契约：待答期间**先判唤醒词**（纯本地拼音匹配，不打云端）——命中即
  // 弃掉本题（POST /api/task/{sid}/stop 投毒丸解除后端 ask() 阻塞），唤醒词后面的指令
  // 作为新一轮发出；没命中才照旧当答案。旧实现把开口直接当答案，正是要修的 P0。
  //
  // Contract after the unlimited answer window: while awaiting, the wake word is judged
  // FIRST (pure local pinyin match, no cloud call) — a hit abandons this question
  // (POST /api/task/{sid}/stop poisons the backend's blocked ask()) and sends the trailing
  // command as a new round; a miss is still the answer. The old behaviour treated any
  // speech as the answer — the P0 this fixes.
  if (ARGS.skip.includes('2')) {
    record('2', '待答说唤醒词 → 弃题开新轮', 'SKIP', '命令行指定跳过')
  } else {
    say('\n' + '─'.repeat(72))
    say('第 2 项：待答期间说唤醒词 → 弃题开新轮')
    say('─'.repeat(72))
    const sc = await newScenario(page, '帮我整理一下下载文件夹')
    if (!sc.ok) {
      record('2', '待答说唤醒词 → 弃题开新轮', 'FAIL',
        '发出消息后 90s 内没有进入 awaiting_answer，场景未搭成')
    } else {
      say(`\n助手提问：${sc.question}`)
      say(`\n👉 请对着麦克风说「${keyword}，今天几点」——唤醒词 + 一个新指令，连起来说。`)
      say('   预期：本题被弃掉，指令作为**新一轮**发出；唤醒词不会被当成本题的答案。')
      // 同第 1 项：窗口开在用户开口之前（先说、后按回车）。
      // As in check 1: the window opens before the user speaks.
      const t0 = Date.now()
      await enter('   说完后按回车开始判定… ')
      // 三类客观证据，先到先回：
      //   stop —— 弃题毒丸已投（/api/task/{sid}/stop）
      //   utter —— 指令起了新一轮（/api/voice/utter）
      //   answer —— 语音被当成了本题答案（/api/voice/answer，弃题路径失守的信号）
      // stop 之后 utter 还要等 done(cancelled) 回流 + outbox 连发，所以二者齐了才停。
      // Three pieces of objective evidence; return on the first arrival: stop (abandon
      // poison pill), utter (the command started a new round), answer (the speech was
      // taken as this question's answer — the abandon path failed). After stop, utter
      // still awaits the done(cancelled) round-trip plus the outbox flush, so wait for both.
      await waitFor(() => {
        const answer = reqs.since(t0, /^\/api\/voice\/answer$/)
        const stop = reqs.since(t0, /^\/api\/task\/[^/]+\/stop$/)
        const utter = reqs.since(t0, /^\/api\/voice\/utter$/)
        return answer.length || (stop.length && utter.length) ? { answer, stop, utter } : null
      }, 90000)
      const answer = reqs.since(t0, /^\/api\/voice\/answer$/)
      const stop = reqs.since(t0, /^\/api\/task\/[^/]+\/stop$/)
      const utter = reqs.since(t0, /^\/api\/voice\/utter$/)
      const transcribe = reqs.since(t0, /^\/api\/voice\/transcribe$/)
      const after = await getState(page)
      const evidence =
        `按回车后状态：${after}\n窗口内相关请求：\n` +
        reqs.since(t0, /^\/api\/(voice|task)\//)
          .map(r => `  ${r.method} ${r.path}  body=${r.body}`).join('\n')
      // 判定树（证据 → 结论，采不到证据绝不 PASS）：
      // 1. 有 answer：转写文本含唤醒词 = 检测失守（FAIL）；不含 = 说的不是唤醒词/ASR
      //    没听清，场景没搭成（INCONCLUSIVE）。
      // 2. 无 answer、stop 与 utter 齐 = 弃题 + 新轮（PASS）。
      // 3. 有 stop 无 utter：多半只说了裸唤醒词（弃题生效但没指令可发），场景没搭成。
      // 4. 什么都没有：转写都没发生，场景没搭成。
      // Decision tree (evidence → verdict; no evidence, never PASS): (1) an answer means
      // either the detector failed (transcript contains the keyword → FAIL) or the
      // operator's speech was not a wake word / ASR missed it (→ INCONCLUSIVE);
      // (2) stop+utter with no answer = abandon + new round (PASS); (3) stop without
      // utter is most likely a bare wake word (abandon worked, nothing to send) →
      // scenario not set up; (4) nothing at all → transcription never happened.
      let status, detail
      if (answer.length) {
        const body = answer[0].body || ''
        if (body.includes(keyword)) {
          status = 'FAIL'
          detail = `语音被当成本题答案提交（/api/voice/answer body 含「${keyword}」），弃题路径失守 —— 待答先判唤醒词未生效`
        } else {
          status = 'INCONCLUSIVE'
          detail = `提交了 /api/voice/answer 但 body 不含唤醒词（${body.slice(0, 120)}）—— 说的可能不是唤醒词或 ASR 没听清，场景未搭成（不是通过）`
        }
      } else if (stop.length && utter.length) {
        status = 'PASS'
        detail = `弃题已投（/api/task/*/stop ×${stop.length}）、唤醒词未被当答案（无 /api/voice/answer），指令发起新一轮 /api/voice/utter（${((Date.now() - t0) / 1000).toFixed(1)}s）`
      } else if (stop.length) {
        status = 'INCONCLUSIVE'
        detail = `弃题已投（stop ×${stop.length}）但 90s 内无新 /api/voice/utter —— 多半只说了裸唤醒词、没带指令，场景未搭成（不是通过）`
      } else {
        status = 'INCONCLUSIVE'
        detail = `90s 内未见 stop/utter/answer 任何一者（transcribe ×${transcribe.length}）—— 语音没被转写或没开口，场景未搭成（不是通过）`
      }
      record('2', '待答说唤醒词 → 弃题开新轮', status, detail, evidence)
    }
  }

  // ── 第 3 项：播报含唤醒词不自触发 ──
  if (ARGS.skip.includes('3')) {
    record('3', '播报含唤醒词 → 不自触发', 'SKIP', '命令行指定跳过')
  } else if (!speakOn) {
    record('3', '播报含唤醒词 → 不自触发', 'INCONCLUSIVE',
      '「播报」开关关闭，助手的播报不会出声，这项测不到（不是通过）')
  } else {
    say('\n' + '─'.repeat(72))
    say('第 3 项：助手播报含唤醒词的文本 → 不应自触发唤醒')
    say('─'.repeat(72))
    await runSelfTriggerCheck({ page, keyword, reqs })
  }
}

/**
 * 通话模式验收：双击进入 → 真人直接说一句指令（不喊唤醒词）→ 客观证据三件套：
 * (1) /api/voice/call/segment 有请求 (2) /api/voice/utter 出现（命中送编排）
 * (3) 全程无 /api/voice/wake* 请求。采不到证据一律 INCONCLUSIVE，绝不 PASS。
 *
 * Call-mode acceptance: double-click to enter → the human speaks a command directly
 * (no wake word) → three pieces of objective evidence: (1) call/segment requests,
 * (2) an utter request (a hit reached the orchestrator), (3) zero voice/wake* requests.
 * No evidence = INCONCLUSIVE, never PASS.
 */
async function runCallCheck(page, reqs) {
  if (ARGS.skip.includes('4')) {
    record('4', '通话模式免唤醒指令', 'SKIP', '命令行指定跳过')
    return
  }
  say('▶ 第 4 项：通话模式（免唤醒）')
  const t0 = Date.now()
  try {
    await page.locator('.float-trigger').dblclick({ timeout: 5000 })
  } catch (e) {
    record('4', '通话模式免唤醒指令', 'INCONCLUSIVE', `双击悬浮球失败：${e.message}`)
    return
  }
  await sleep(1200)
  const listening = await page.locator('text=通话聆听中').count().catch(() => 0)
  if (!listening) {
    record('4', '通话模式免唤醒指令', 'INCONCLUSIVE', '状态胶囊未显示「通话聆听中」（未进入通话态）')
    return
  }
  await say('    5 秒后请**直接**说一句完整指令（例如「今天几号」），不要喊唤醒词')
  await countdown(5, '请开口')
  const deadline = Date.now() + 30000
  let utter = []
  while (Date.now() < deadline) {
    utter = reqs.since(t0, /^\/api\/voice\/utter$/)
    if (utter.length) break
    await sleep(500)
  }
  const segs = reqs.since(t0, /^\/api\/voice\/call\/segment$/)
  const wakes = reqs.since(t0, /^\/api\/voice\/wake/)
  const evidence = `segment=${segs.length} utter=${utter.length} wake=${wakes.length}` +
    (utter[0] ? ` utter_body=${utter[0].body.slice(0, 160)}` : '')
  // 退出通话（复位，不影响后续人工检查）
  try { await page.locator('.float-trigger').dblclick({ timeout: 3000 }) } catch { /* ignore */ }

  if (!segs.length) {
    record('4', '通话模式免唤醒指令', 'INCONCLUSIVE', '未见 call/segment 请求（录音/会话链路没跑起来）', evidence)
    return
  }
  if (!utter.length) {
    record('4', '通话模式免唤醒指令', 'INCONCLUSIVE', 'segment 有、utter 无（漏斗未命中或闸门误杀——人工核对 audit.log call-funnel 行）', evidence)
    return
  }
  if (wakes.length) {
    record('4', '通话模式免唤醒指令', 'FAIL', `通话期出现了 ${wakes.length} 次唤醒判定请求（链路串了）`, evidence)
    return
  }
  record('4', '通话模式免唤醒指令', 'PASS', '免唤醒段落进漏斗并命中送编排，全程无唤醒判定', evidence)
}

/**
 * 第 3 项的实现：让助手**用自己正常的播报链路**念出含唤醒词的文本，播报期间观察
 * 「有没有音频分段被录下来并上传」。
 *
 * Implementation of check 3: have the assistant speak a wake-word-containing text through its
 * *own normal playback path* and watch whether any audio segment is recorded and uploaded
 * during playback.
 *
 * 新架构下的等价危险：旧的「唤醒引擎自触发」已不存在（Vosk 引擎与模型都删了），剩下的是
 * **助手自己的声音被麦克风采到、被 VAD 切段、当成用户说话上传云端**。所以判据换成：
 *
 *   1) **原因**：播报期间麦克风必须是关着的（活着的音频轨道数为 0）—— 由麦克风探针直接测。
 *   2) **结果**：播报窗口内不得出现任何携带音频的上传
 *      （`/api/voice/wake` 唤醒判定、`/api/voice/transcribe` 转写、`/api/voice/answer` 作答，
 *      这三条都是分段录音器 `onSegment` 的下游出口）。
 *
 * 两条都拿不到证据时一律 **INCONCLUSIVE，绝不 PASS**：
 *   - 助手没念出唤醒词（场景没搭成）
 *   - 采样没覆盖到播报窗口
 *   - 麦克风探针不可用（读不到轨道数）
 *   - 播报**前**麦克风本来就是关的（没有东西可挡，此时「播报期没上传」不构成证据）
 *
 * The equivalent hazard under the new architecture: the old "wake engine self-triggers" is gone
 * (the Vosk engine and its model were deleted); what remains is the assistant's **own voice
 * caught by the mic, segmented by the VAD, and uploaded as if the user had spoken**. So the
 * criteria become:
 *
 *   1) the *cause*: the mic must be closed during playback (0 live audio tracks) — measured
 *      directly by the mic probe;
 *   2) the *effect*: no audio-bearing upload may appear inside the playback window
 *      (`/api/voice/wake` detection, `/api/voice/transcribe`, `/api/voice/answer` — all three
 *      are downstream of the segment recorder's `onSegment`).
 *
 * When neither can be evidenced the verdict is **INCONCLUSIVE, never PASS**: the assistant never
 * spoke the keyword (scenario not set up), the sampling missed the playback window, the mic
 * probe is unavailable (no track count), or the mic was already closed *before* playback (there
 * was nothing to gate, so "no upload during playback" proves nothing).
 *
 * 关键点：必须走 App 自己的播报（它才会去设置 speaking 并触发暂停监听的门控）。直接注入
 * speechSynthesis.speak 绕过了门控，那样测的是浏览器而不是本功能 —— 假通过。
 *
 * The crux: it must go through the app's own playback (only that sets `speaking` and engages
 * the pause-listening gate). Injecting speechSynthesis.speak directly bypasses the gate, which
 * would test the browser rather than this feature — a false pass.
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

    // 采样必须在发消息**之前**启动 —— 门控动作发生在播报期间，播报一结束监听就恢复了，
    // 事后补采会看到「一切正常」的假象。
    // Sampling must start *before* the message: the gate acts during playback and listening is
    // restored the moment it ends, so sampling afterwards would show a falsely clean picture.
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
    // 别把成因一口咬定成「助手不肯念」：TTS 引擎若设为「后端 API」（engine=api），
    // 声音由 <audio> 播放，浏览器端 speechSynthesis.speak 根本不会被调用，本项在浏览器侧
    // 什么都看不到。两条成因行动完全不同，所以都写出来。
    // Do not pin the cause on "the assistant refused to say it": with the backend API TTS engine
    // (engine=api) the sound comes out of an <audio> element, speechSynthesis.speak is never
    // called, and the browser side sees nothing. The two causes need different actions, so both
    // are stated.
    record('3', '播报含唤醒词 → 不自触发', 'INCONCLUSIVE',
      `浏览器端没有观察到助手用 speechSynthesis 念出「${keyword}」，播报里没有唤醒词就测不到自触发 —— 不是通过。` +
      `若助手确实出声了，多半是播报引擎设成了「后端 API」（声音走 <audio>，浏览器侧看不到）：` +
      `请在播报设置里切回浏览器引擎后重跑`,
      `实际播报文本：${spoken || '(空)'}`)
    return
  }

  const samples = sampler?.samples ?? []
  const playback = samples.filter(s => s.speaking)
  const stateSeq = samples.reduce((a, s) => (a.at(-1) === s.state || !s.state ? a : [...a, s.state]), [])
  const firstPlayIdx = samples.findIndex(s => s.speaking)
  const lastPlayIdx = firstPlayIdx < 0 ? -1 : samples.findLastIndex(s => s.speaking)
  const before = samples.slice(0, firstPlayIdx < 0 ? 0 : firstPlayIdx)
  const after = samples.slice(lastPlayIdx < 0 ? samples.length : lastPlayIdx + 1)

  // 播报前是否真有麦克风开着 —— 这是「门控有东西可挡」的前提，也是 PASS 不空洞的根据。
  // 采样里出现 micLive>0 即证明当时确有活轨道。
  // Whether a mic was genuinely open before playback — the precondition that the gate had
  // something to gate, and what keeps a PASS from being vacuous. A micLive>0 sample proves a
  // live track existed at that moment.
  const micLiveBefore = before.some(s => s.micLive > 0)
  // 播报期活轨道数：取窗口内的最大值（判 FAIL 用「曾经开着」而非「某一瞬间开着」，更严）。
  // Live tracks during playback: the maximum across the window (FAIL on "was ever open", which
  // is stricter than "was open at one instant").
  const playbackMaxLive = playback.length ? Math.max(...playback.map(s => s.micLive ?? -1)) : -1
  const probeUsable = playback.some(s => s.micLive !== null)

  // 播报窗口内的音频上传。窗口 = [首个播报采样, 末个播报采样 + 500ms]。
  //
  // 起点**不**往前留余量：采样本身就是「播报已开始」的**事后**观测（最多晚 150ms），已经自带
  // 前瞻；再往前扩只会把「用户自己说话、在播报前一瞬结束的那一段」误算成自触发。
  // 门控是否失效由麦克风探针负责抓（见上），这里只做佐证。
  // 末尾留 500ms：播报一结束监听就恢复，但新的一台录音器要取流 + 说满 minSpeechMs + 静音
  // 1.5s 才可能产出分段，远超过这个余量，所以不会把恢复后的用户说话算进来。
  //
  // Audio uploads inside the playback window: [first speaking sample, last speaking sample + 500ms].
  //
  // No lead-in margin: the sample is itself a *post hoc* observation of "playback started" (up to
  // 150ms late), so it already leads; widening it further would only pull in a segment of the
  // user's own speech that ended just before playback. Whether the gate failed is the mic probe's
  // job (above); this is corroboration. The 500ms tail covers the resume: listening comes back the
  // moment playback ends, but a fresh recorder needs to acquire a stream, accumulate minSpeechMs
  // and then 1.5s of silence before it can emit a segment — far beyond that margin.
  // 注：采样时间戳取自浏览器 Date.now()，请求时间戳取自 Node Date.now() —— 本脚本驱动的是
  // 本机 Chrome，两者同一口系统钟。
  // Note: sample timestamps come from the browser's Date.now() and request timestamps from Node's;
  // the harness drives a local Chrome, so both read the same system clock.
  const winStart = firstPlayIdx < 0 ? Infinity : samples[firstPlayIdx].t
  const winEnd = lastPlayIdx < 0 ? -Infinity : samples[lastPlayIdx].t + 500
  const AUDIO_UPLOAD = /^\/api\/voice\/(wake|transcribe|answer)$/
  const uploaded = reqs.list.filter(r => r.t >= winStart && r.t <= winEnd && AUDIO_UPLOAD.test(r.path))
  const voiceAny = reqs.list.filter(r => r.t >= winStart && r.t <= winEnd && r.path.startsWith('/api/voice/'))

  let status, detail
  if (!playback.length) {
    status = 'INCONCLUSIVE'
    detail = '本次采样没有捕捉到 speechSynthesis 播报窗口，无法判定（不是通过）'
  } else if (!probeUsable) {
    status = 'INCONCLUSIVE'
    detail = '麦克风探针不可用（读不到活轨道数），无法证明播报期麦克风确实关着（不是通过）'
  } else if (!micLiveBefore) {
    status = 'INCONCLUSIVE'
    detail = '播报前采样里麦克风就已经是关着的 —— 没有东西可挡，「播报期没上传」不构成证据（不是通过）'
  } else if (uploaded.length) {
    status = 'FAIL'
    detail = `播报期间出现了 ${uploaded.length} 条携带音频的上传（${uploaded.map(r => r.path).join('、')}）—— 助手自己的声音被 VAD 切段并上传，即自触发`
  } else if (playbackMaxLive > 0) {
    status = 'FAIL'
    detail = `播报期间麦克风仍有 ${playbackMaxLive} 条活轨道 —— 暂停监听的门控没有生效（未释放麦克风），只是这次恰好没被上传`
  } else {
    status = 'PASS'
    detail = `播报期间麦克风已释放（${playback.length} 次采样活轨道均为 0，播报前确有 ${before.filter(s => s.micLive > 0).length} 次采样开着），且窗口内无任何音频上传`
  }

  record('3', '播报含唤醒词 → 不自触发', status, detail,
    `播报文本：${spoken.slice(0, 160)}\n` +
    `麦克风活轨道数 —— 播报前曾开着 ${before.filter(s => s.micLive > 0).length}/${before.length} 次采样，` +
    `播报期最大 ${playbackMaxLive < 0 ? 'n/a' : playbackMaxLive}，播报后最大 ${Math.max(-1, ...after.map(s => s.micLive ?? -1))}\n` +
    `（播报前开着、播报期归零 = 门控确实生效；播报期仍大于 0 则判 FAIL）\n` +
    `播报窗口内音频上传（/api/voice/wake|transcribe|answer）：${uploaded.length} 条\n` +
    `播报窗口内 /api/voice/* 请求：${voiceAny.length ? voiceAny.map(r => `${r.method} ${r.path}`).join('、') : '(无)'}\n` +
    `状态序列：${stateSeq.join(' → ')}\n` +
    `注：` +
    `「播报期无音频上传」这一半取决于扬声器→麦克风的实际通路（扬声器静音时它无判别力）；\n` +
    `    「播报期麦克风已释放」这一半直接测轨道，不依赖声学通路，任何情况下都可证伪。`)
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
