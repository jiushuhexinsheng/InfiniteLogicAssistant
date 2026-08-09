import { ref, computed } from 'vue'
import { api } from '../api'
import { STATE_VISUALS, resolveStateLabel, type StateVisual } from './useAssistantVisuals'
import type { WakeWordConfig, VadConfig } from '../types'

// ─── 状态机 ───
export type AsstState =
  | 'idle'
  | 'listening'
  | 'recording'
  | 'transcribing'
  | 'thinking'
  | 'tool_calling'
  | 'responding'
  | 'done'
  | 'error'

export interface ToolCall {
  id: string
  name: string
  args: Record<string, any>
  result?: string
  status: 'pending' | 'running' | 'done' | 'failed'
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  text: string
  toolCalls?: ToolCall[]
  timestamp: number
}

// ─── 可用工具（扩展点：在此新增工具描述，并在 handleAction 中实现对应分支）───
const TOOLS = [
  {
    name: 'chat',
    description: '纯对话，无需调用工具。args: reply(回复内容)',
  },
]

// ─── LLM System Prompt ───
const SYSTEM_PROMPT = `你是一个智能语音助手，名字叫"小逻"。用中文回复，简洁友好（一般不超过3句话）。

你的能力：
1. 日常对话 — 打招呼、解答问题、闲聊
2. 将来可扩展工具调用（如查信息、打开网页等）

当用户需要执行操作时，返回 JSON（不要加 markdown 代码块）：
{"action":"<工具名>","args":{...},"reply":"<对用户说的话>"}

如果是纯聊天，返回：
{"action":"chat","args":{"reply":"<回复>"},"reply":"<回复>"}

可用工具：
${TOOLS.map(t => `- ${t.name}: ${t.description}`).join('\n')}`

// ─── composable ───

/** config.yaml 的 model_path 可能是目录名（如 "models/vosk-model-small-cn-0.22"），
 *  而 vosk.createModel 需要指向可下载的 .tar.gz 文件 URL。归一化为服务端相对 URL。 */
function resolveModelPath(p?: string): string {
  const def = '/models/vosk-model-small-cn-0.22.tar.gz'
  if (!p) return def
  let path = p.trim()
  if (!path.startsWith('/')) path = '/' + path
  if (!/\.tar\.gz$/i.test(path)) path = path + '.tar.gz'
  return path
}

export function useAssistant() {
  // ── 状态 ──
  const state = ref<AsstState>('idle')
  const messages = ref<ChatMessage[]>([])
  const expanded = ref(false)
  const wakeEnabled = ref(false)
  const partialText = ref('')
  const statusLine = ref('')

  // 唤醒词配置（init 时从 /api/config 合并）
  let wakeConfig: WakeWordConfig = { enabled: true, keyword: '小逻小逻', sensitivity: 0.5, model_path: '/models/vosk-model-small-cn-0.22.tar.gz' }
  let vadConfig: VadConfig = { silence_threshold: 0.02, silence_duration_ms: 1500, max_duration_ms: 10000 }
  const wakeKeyword = ref(wakeConfig.keyword)  // 响应式 keyword，供 UI 提示与状态文案

  // ── 录音管线 ──
  let wakeRecorder: MediaRecorder | null = null
  let wakeChunks: Blob[] = []
  let silenceTimer: ReturnType<typeof setInterval> | null = null
  let maxTimer: ReturnType<typeof setTimeout> | null = null
  let vadAudioCtx: AudioContext | null = null

  // ── 唤醒词引擎 ──
  let modelLoaded = false

  async function initWakeModel() {
    if (typeof WakeWordEngine === 'undefined') {
      console.warn('[Asst] WakeWordEngine missing')
      return false
    }
    if (modelLoaded) return true
    try {
      statusLine.value = '正在加载语音模型...'
      const ok = await WakeWordEngine.init({
        modelPath: wakeConfig.model_path,
        keyword: wakeConfig.keyword,
        sensitivity: wakeConfig.sensitivity,
      })
      modelLoaded = ok
      statusLine.value = ok ? '' : '模型加载失败'
      return ok
    } catch (e) {
      console.error('[Asst] model init fail:', e)
      statusLine.value = '模型加载失败'
      return false
    }
  }

  function playBeep() {
    try {
      const ctx = new (window.AudioContext || (window as any).webkitAudioContext)()
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.connect(gain); gain.connect(ctx.destination)
      osc.type = 'sine'
      osc.frequency.setValueAtTime(800, ctx.currentTime)
      osc.frequency.linearRampToValueAtTime(1000, ctx.currentTime + 0.1)
      gain.gain.setValueAtTime(0.3, ctx.currentTime)
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.2)
      osc.start(ctx.currentTime)
      osc.stop(ctx.currentTime + 0.2)
      setTimeout(() => ctx.close().catch(() => {}), 500)
    } catch { /* mute */ }
  }

  function clearTimers() {
    if (silenceTimer) { clearInterval(silenceTimer); silenceTimer = null }
    if (maxTimer) { clearTimeout(maxTimer); maxTimer = null }
    if (vadAudioCtx) { try { vadAudioCtx.close() } catch { /* ignore */ } vadAudioCtx = null }
  }

  function stopRecording() {
    clearTimers()
    if (wakeRecorder && wakeRecorder.state === 'recording') {
      wakeRecorder.stop()
    }
  }

  function startVAD(stream: MediaStream) {
    let analyser: AnalyserNode | null = null
    try {
      // 关闭上一次残留的 AudioContext
      if (vadAudioCtx) { try { vadAudioCtx.close() } catch { /* ignore */ } }
      vadAudioCtx = new (window.AudioContext || (window as any).webkitAudioContext)()
      const ctx = vadAudioCtx
      const source = ctx.createMediaStreamSource(stream)
      analyser = ctx.createAnalyser()
      analyser.fftSize = 2048
      analyser.smoothingTimeConstant = 0.3
      source.connect(analyser)
    } catch (e) { return }

    const threshold = vadConfig.silence_threshold || 0.02
    const silenceMs = vadConfig.silence_duration_ms || 1500
    const checkInterval = 100
    const maxSilence = Math.ceil(silenceMs / checkInterval)
    let silenceCount = 0
    let elapsed = 0
    const minSpeakTime = 2000

    silenceTimer = setInterval(() => {
      if (!analyser || !wakeRecorder || wakeRecorder.state !== 'recording') {
        clearTimers()
        return
      }
      elapsed += checkInterval
      const dataArray = new Uint8Array(analyser.fftSize)
      analyser.getByteTimeDomainData(dataArray)
      let sum = 0
      for (let i = 0; i < dataArray.length; i++) {
        const v = (dataArray[i] - 128) / 128
        sum += v * v
      }
      const rms = Math.sqrt(sum / dataArray.length)

      if (elapsed < minSpeakTime) return
      if (rms < threshold) {
        silenceCount++
        if (silenceCount >= maxSilence) {
          stopRecording()
        }
      } else {
        silenceCount = 0
      }
    }, checkInterval)
  }

  function startMaxTimer() {
    maxTimer = setTimeout(() => {
      console.log('[Asst] max duration reached')
      stopRecording()
    }, vadConfig.max_duration_ms || 10000)
  }

  // ── 唤醒检测回调 ──
  function onWakeDetected() {
    console.log('[Asst] WAKE!')
    state.value = 'recording'
    playBeep()

    const stream = WakeWordEngine.getStream()
    if (!stream) { state.value = 'listening'; return }

    wakeChunks = []
    let mimeType = 'audio/webm'
    if (!MediaRecorder.isTypeSupported(mimeType)) {
      mimeType = 'audio/webm;codecs=opus'
      if (!MediaRecorder.isTypeSupported(mimeType)) mimeType = ''
    }
    const opts: MediaRecorderOptions = {}
    if (mimeType) opts.mimeType = mimeType

    try {
      wakeRecorder = new MediaRecorder(stream, opts)
    } catch (e) {
      console.error('[Asst] MediaRecorder fail:', e)
      state.value = 'listening'
      return
    }

    wakeRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) wakeChunks.push(e.data)
    }

    wakeRecorder.onstop = async () => {
      clearTimers()
      if (wakeChunks.length === 0) { state.value = 'listening'; return }

      state.value = 'transcribing'
      const blob = new Blob(wakeChunks, { type: mimeType || 'audio/webm' })
      wakeChunks = []
      console.log('[Asst] recording done, size:', blob.size)

      await handleTranscript(blob)

      // 回到聆听状态
      setTimeout(() => {
        if (state.value === 'done' || state.value === 'error') {
          state.value = 'listening'
        }
      }, 3000)
    }

    wakeRecorder.start(1000)
    startVAD(stream)
    startMaxTimer()
  }

  // ── ASR 转写 ──
  async function handleTranscript(blob: Blob) {
    try {
      const r = await api.transcribe(blob)
      if (r.ok && r.text) {
        const text = r.text.trim()
        if (!text) { state.value = 'listening'; return }
        partialText.value = text
        addMessage('user', text)
        await handleLLM(text)
      } else {
        addMessage('system', '转写失败: ' + (r.error || '无结果'))
        state.value = 'listening'
      }
    } catch (e: any) {
      console.error('[Asst] transcribe error:', e)
      addMessage('system', '转写异常: ' + (e.message || ''))
      state.value = 'error'
    }
  }

  // ── LLM 对话 ──
  async function handleLLM(userText: string) {
    state.value = 'thinking'

    // 构建对话历史
    const history: { role: string; content: string }[] = []
    history.push({ role: 'system', content: SYSTEM_PROMPT })
    for (const m of messages.value.slice(-6)) {
      if (m.role === 'user') history.push({ role: 'user', content: m.text })
      else if (m.role === 'assistant') {
        let content = m.text
        // 附加工具执行结果，供后续指令引用
        if (m.toolCalls?.length) {
          const results = m.toolCalls
            .map((tc) => `[工具 ${tc.name} 执行结果]\n${tc.result || ''}`)
            .join('\n\n')
          content = `${content}\n\n${results}`
        }
        history.push({ role: 'assistant', content })
      }
    }

    try {
      const resp = await fetch('/api/ai/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: history }),
      })
      const data = await resp.json()
      if (!data.ok) throw new Error(data.error || 'LLM error')

      const raw = data.text || ''
      // 解析 JSON action — 兼容 markdown 包裹 + 裸 JSON
      let parsed: any = null
      const cleaned = raw.replace(/```(?:json)?\s*/g, '').replace(/```/g, '').trim()
      const jsonMatch = cleaned.match(/\{[\s\S]*"action"[\s\S]*\}/)
      if (jsonMatch) {
        try { parsed = JSON.parse(jsonMatch[0]) } catch { /* ignore */ }
      }
      if (!parsed) {
        try { parsed = JSON.parse(cleaned) } catch { /* ignore */ }
      }

      if (parsed && parsed.action) {
        await handleAction(parsed)
      } else {
        // 纯文本回复
        state.value = 'responding'
        addMessage('assistant', raw)
        speakText(raw)
        setTimeout(() => { if (state.value === 'responding') state.value = 'done' }, 2000)
      }
    } catch (e: any) {
      console.error('[Asst] LLM error:', e)
      addMessage('assistant', '抱歉，我暂时无法处理，请稍后再试')
      state.value = 'error'
    }
  }

  // ── 工具调用 ──
  async function handleAction(parsed: { action: string; args: Record<string, any>; reply?: string }) {
    const { action, args = {}, reply = '' } = parsed
    const toolCalls: ToolCall[] = [{
      id: genId(),
      name: action,
      args,
      status: 'running',
    }]

    state.value = 'tool_calling'
    let toolResult = ''

    try {
      switch (action) {
        case 'chat': {
          toolResult = args.reply || reply || ''
          toolCalls[0].status = 'done'
          toolCalls[0].result = toolResult
          break
        }
        default: {
          // 未知操作 — 降级为对话回复
          toolResult = reply || `收到，正在处理...`
          toolCalls[0].status = 'done'
          toolCalls[0].result = toolResult
        }
      }
    } catch (e: any) {
      toolCalls[0].status = 'failed'
      toolCalls[0].result = e.message || '执行失败'
    }

    const displayText = reply || toolResult
    addMessage('assistant', displayText, toolCalls)
    // 浏览器语音播报
    speakText(reply || toolResult)

    // 工具执行完后，让 LLM 总结结果
    if (action !== 'chat') {
      state.value = 'thinking'
      try {
        const summaryResp = await fetch('/api/ai/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            messages: [
              { role: 'system', content: '你是智能语音助手小逻。用户执行了一个操作，请用一句话告知结果。' },
              { role: 'user', content: `操作: ${action}, 结果: ${toolResult}` },
            ],
          }),
        })
        const sdata = await summaryResp.json()
        if (sdata.ok && sdata.text) {
          // 更新最后一条消息
          const last = messages.value[messages.value.length - 1]
          if (last && last.role === 'assistant') {
            last.text = sdata.text
          }
        }
      } catch { /* ignore */ }
    }

    state.value = 'done'
  }

  // ── 消息管理 ──
  function genId() {
    try { return crypto.randomUUID() } catch { return Date.now().toString(36) + Math.random().toString(36).slice(2, 8) }
  }

  function addMessage(role: ChatMessage['role'], text: string, toolCalls?: ToolCall[]) {
    messages.value.push({
      id: genId(),
      role,
      text,
      toolCalls,
      timestamp: Date.now(),
    })
    // 最多保留 50 条
    if (messages.value.length > 50) messages.value.shift()
  }

  // ── 开启/关闭唤醒 ──
  async function toggleWake() {
    console.log('[Asst] toggleWake called, current state:', state.value, 'modelLoaded:', modelLoaded)
    statusLine.value = ''

    if (state.value === 'idle' || state.value === 'done' || state.value === 'error') {
      // ── 开启 ──
      if (typeof WakeWordEngine === 'undefined') {
        console.error('[Asst] WakeWordEngine not defined')
        statusLine.value = '唤醒引擎未加载'
        state.value = 'error'
        return
      }

      if (!modelLoaded) {
        statusLine.value = '正在加载语音模型...'
        state.value = 'listening' // 先切到 listening 让用户看到变化
        console.log('[Asst] loading model...')
        try {
          const ok = await initWakeModel()
          if (!ok) {
            console.error('[Asst] model init failed')
            statusLine.value = '模型加载失败'
            state.value = 'error'
            return
          }
        } catch (e: any) {
          console.error('[Asst] model init exception:', e)
          statusLine.value = '模型加载异常: ' + (e.message || '')
          state.value = 'error'
          return
        }
      }

      statusLine.value = '正在启动唤醒...'
      console.log('[Asst] starting WakeWordEngine...')
      try {
        // start() 内部会 catch 错误并返回 false（如麦克风被系统/浏览器拦截），需检查返回值
        const started = await WakeWordEngine.start(onWakeDetected, (info: any) => {
          partialText.value = info.partial || ''
        })
        if (!started) {
          console.warn('[Asst] WakeWordEngine.start returned false')
          state.value = 'error'
          statusLine.value = '麦克风启动失败，请检查系统/浏览器麦克风权限'
          return
        }
        wakeEnabled.value = true
        state.value = 'listening'
        statusLine.value = ''
        console.log('[Asst] listening started!')
      } catch (e: any) {
        console.error('[Asst] WakeWordEngine.start failed:', e)
        state.value = 'error'
        statusLine.value = '麦克风访问被拒绝或失败'
      }
    } else {
      // ── 关闭 ──
      console.log('[Asst] stopping...')
      try { WakeWordEngine.stop() } catch (e) { console.error('[Asst] stop error:', e) }
      wakeEnabled.value = false
      state.value = 'idle'
      partialText.value = ''
      statusLine.value = ''
    }
  }

  // ── 初始化 ──
  function init(config?: { wake?: Partial<WakeWordConfig>; vad?: Partial<VadConfig> }) {
    if (config?.wake) {
      wakeConfig = { ...wakeConfig, ...config.wake, model_path: resolveModelPath(config.wake.model_path) }
      wakeKeyword.value = wakeConfig.keyword || wakeKeyword.value
    }
    if (config?.vad) Object.assign(vadConfig, config.vad)
    if (typeof WakeWordEngine !== 'undefined') {
      state.value = 'idle'
      // 预热模型
      initWakeModel()
    } else {
      state.value = 'idle'
      console.warn('[Asst] WakeWordEngine not loaded, wake disabled')
    }
  }

  function destroy() {
    try { WakeWordEngine.stop() } catch { /* ignore */ }
    clearTimers()
    if (wakeRecorder && wakeRecorder.state !== 'inactive') {
      try { wakeRecorder.stop() } catch { /* ignore */ }
    }
  }

  // ── 清空消息 ──
  function clearMessages() {
    messages.value = []
  }

  // ── 浏览器语音播报 ──
  function speakText(text: string) {
    if (!text || typeof window === 'undefined') return
    try {
      // 先 cancel 避免队列堆积
      window.speechSynthesis.cancel()
      const u = new SpeechSynthesisUtterance(text.replace(/\n/g, '，'))
      u.lang = 'zh-CN'
      u.rate = 1.0
      u.pitch = 1.0
      // 部分浏览器需在用户手势上下文中调用，延迟到下一帧
      requestAnimationFrame(() => {
        try { window.speechSynthesis.speak(u) } catch { /* ignore */ }
      })
    } catch { /* ignore */ }
  }

  // ── 状态视觉（数据驱动，来自 useAssistantVisuals）──
  const visual = computed<StateVisual>(() => STATE_VISUALS[state.value] || STATE_VISUALS.idle)
  const stateLabel = computed(() => resolveStateLabel(visual.value, wakeKeyword.value))
  const stateColor = computed(() => visual.value.color)

  return {
    // 状态
    state,
    visual,
    stateLabel,
    stateColor,
    messages,
    expanded,
    wakeEnabled,
    wakeKeyword,
    partialText,
    statusLine,
    // 方法
    init,
    destroy,
    toggleWake,
    clearMessages,
  }
}
