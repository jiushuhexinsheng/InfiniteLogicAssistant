import { ref, computed } from 'vue'
import { api, streamChat } from '../api'
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
  durationMs?: number
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  text: string
  toolCalls?: ToolCall[]
  timestamp: number
}

// ─── LLM System Prompt（工具由后端 @tool 注册中心注入，前端不再约定 JSON action）───
const SYSTEM_PROMPT = `你是一个智能语音助手，名字叫"小逻"。用中文回复，简洁友好（一般不超过3句话）。
你的能力：日常对话、解答问题、使用系统提供的工具（如查时间/计算/搜索/天气）。`

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

  // ── 流式对话中止句柄（取消/停止按钮用）──
  let abortController: AbortController | null = null

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
        await runTurn()
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
  // 用当前 messages 构建 OpenAI 消息历史（工具结果以文本拼入 assistant content，供多轮引用）
  function buildHistory(): { role: string; content: string }[] {
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
    return history
  }

  // 消费后端 SSE 流（ReAct + 工具由后端执行，前端只展示）
  async function runTurn() {
    state.value = 'thinking'
    const history = buildHistory()

    // 中止上一次未结束的流（防并发覆盖）
    abortController?.abort()
    abortController = new AbortController()

    let acc = ''
    let currentMsg: ChatMessage | null = null
    const toolAcc: ToolCall[] = []
    const toolStartMap = new Map<string, number>()

    const ensureMsg = () => {
      if (!currentMsg) {
        currentMsg = { id: genId(), role: 'assistant', text: '', toolCalls: toolAcc, timestamp: Date.now() }
        messages.value.push(currentMsg)
        if (messages.value.length > 50) messages.value.shift()
      }
      return currentMsg
    }

    await streamChat(history, {
      onContent: (t) => {
        state.value = 'responding'
        acc += t
        partialText.value = acc
        ensureMsg().text = acc
      },
      onToolStart: (name, args) => {
        state.value = 'tool_calling'
        const id = genId()
        toolStartMap.set(id, Date.now())
        toolAcc.push({ id, name, args, status: 'running' })
        ensureMsg()
      },
      onToolEnd: (name, status, output) => {
        const tc = toolAcc.find(t => t.name === name && t.status === 'running')
        if (tc) {
          tc.status = status === 'ok' ? 'done' : 'failed'
          tc.result = output
          const st = toolStartMap.get(tc.id)
          if (st != null) tc.durationMs = Date.now() - st
          toolStartMap.delete(tc.id)
        }
      },
      onDone: () => {
        partialText.value = ''
        if (acc.trim()) speakText(acc)
        else if (toolAcc.length) speakText('已完成')
        state.value = 'done'
      },
      onAbort: () => {
        // 用户主动取消（cancelTool 触发），非错误
        partialText.value = ''
        state.value = 'done'
      },
      onError: (msg) => {
        console.error('[Asst] LLM error:', msg)
        addMessage('system', '出错了: ' + msg)
        state.value = 'error'
      },
    }, abortController.signal)
  }

  // ── 工具重试：失败的工具走后端真实重跑，再用修正结果续一轮对话 ──
  async function retryTool(id: string) {
    const m = messages.value.find(msg => msg.toolCalls?.some(tc => tc.id === id))
    const tc = m?.toolCalls?.find(t => t.id === id)
    if (!tc) return

    tc.status = 'running'
    tc.result = ''
    tc.durationMs = undefined
    state.value = 'tool_calling'

    const startTs = Date.now()
    try {
      const r = await api.callTool(tc.name, tc.args || {})
      if (r.ok) {
        tc.status = r.status === 'ok' ? 'done' : 'failed'
        tc.result = r.output || ''
      } else {
        tc.status = 'failed'
        tc.result = r.error || '执行失败'
      }
    } catch (e: any) {
      tc.status = 'failed'
      tc.result = e?.message || '执行失败'
    }
    tc.durationMs = Date.now() - startTs

    // 续一轮对话，让助手基于重试后的工具结果作答
    await runTurn()
  }

  // ── 工具/回复取消：中止后端 SSE 流，本地将运行中的步骤标记为已取消 ──
  function cancelTool(id: string) {
    abortController?.abort()
    abortController = null
    for (const msg of messages.value) {
      msg.toolCalls?.forEach(tc => {
        if (tc.id === id && (tc.status === 'running' || tc.status === 'pending')) {
          tc.status = 'failed'
          tc.result = '已取消'
        }
      })
    }
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
    abortController?.abort()
    abortController = null
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

  // ── 文字输入（与语音共用 LLM 管线）──
  function sendText(text: string) {
    const t = text.trim()
    if (!t) return
    addMessage('user', t)
    void runTurn()
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
    sendText,
    retryTool,
    cancelTool,
  }
}
