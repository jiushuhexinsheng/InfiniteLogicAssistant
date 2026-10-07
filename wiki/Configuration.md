# 配置说明

配置采用 **pydantic 强类型校验 + 双文件分离**（非敏感配置 / 密钥独立存储），
加载实现位于 `core/config/` 包（`loader.py` 读取 + `schema.py` 模型校验）。

## 三个配置源（优先级从低到高）

| 源 | 内容 | 说明 |
|---|---|---|
| `config.yaml` | 非敏感结构（llm / voice / server / mcp / rag / agent / llm_client / tools / vendor_presets） | 由 `config.yaml.example` 复制；经 pydantic 校验，类型 / 范围 / 枚举写错启动即报错 |
| `config.secrets.yaml` | 密钥（`llm/asr/tts.api_key`、`server.api_token`、`profiles.<name>` 每 profile 密钥） | 由 `config.secrets.yaml.example` 复制；**gitignored，不入库** |
| 环境变量 | `LLM_API_KEY` / `ASR_API_KEY` / `TTS_API_KEY` / `SERVER_API_TOKEN` | 段级优先级最高，覆盖 secrets 段默认（profile 级密钥见下） |

**单 profile 密钥解析优先级**：`profile.api_key_env` 指向的环境变量 > `secrets.profiles[name]`
（profile 级密钥）> 段全局环境变量 > secrets 段默认 `api_key` > 旧 `config.yaml` 内联 `api_key`（弃用，仅迁移）。

> profile 级密钥必须高于段级环境变量：段级 `LLM_API_KEY` 属于另一个服务商的 key，
> 若先命中会遮蔽本 profile 在 `config.secrets.yaml` 的真 key → 401 Invalid API Key。

> API 永不回显密钥值：设置页只报「已设置 / 未设置」；密钥写 `config.secrets.yaml` 或环境变量。

## llm — LLM 多 provider

```yaml
llm:
  active: deepseek                 # 当前生效的 profile 名（改 active 切换服务商）
  profiles:
    deepseek:                      # OpenAI 兼容示例
      provider: openai             # 协议：openai / anthropic / gemini
      vendor: deepseek             # 厂商目录 ID（UI 元数据）
      endpoint: "https://api.deepseek.com"   # 基座 URL，不含 /v1（与 chat_path 配对）
      model: "deepseek-chat"
      models: ["deepseek-chat", "deepseek-reasoner"]   # 可用模型列表（设置页「获取模型」可自动拉取）
      api_key_env: "DEEPSEEK_API_KEY"   # 本 profile 专用环境变量名（优先级最高）
      chat_path: "/v1/chat/completions"
      max_tokens: 4096
      temperature: 0.7
      timeout: 60
      compat: {}                   # 兼容开关：stream_options / max_tokens_field
```

内置厂商目录（`core/vendors.py`）：deepseek / openai / qwen / glm / kimi / doubao / qianfan /
xinghuo / minimax / siliconflow / openrouter / ollama / lmstudio / anthropic / gemini / xiaomi-mimo。
设置页「新增 Profile」可从目录一键预填；`config.yaml` 的 `vendor_presets` 可追加 / 覆盖自定义厂商。

## voice — 语音

```yaml
voice:
  wake_word:
    enabled: true
    # 可配多个唤醒词，命中任意一个即唤醒；旧的单数写法 `keyword: 词` 仍兼容
    keywords:
      - 衍衡
      - 洛吉斯
    sensitivity: 0.5
    model_path: ""              # Vosk 时代遗留字段，已无人读，留空即可
  vad:                          # 本地 VAD：静音检测（决定一段从哪开始、到哪结束）
    silence_threshold: 0.02     # 判定「有人在说」的 RMS 阈值
    silence_duration_ms: 1500   # 静音多久算一段说完（决定何时切段）
    max_duration_ms: 10000      # 单段硬上限
    min_speech_ms: 300          # 短于此长度的段直接丢弃（滤爆音）
    upload_throttle_ms: 500     # 两次唤醒判定的最小间隔
    answer_timeout_ms: 8000     # 待答窗口：提问后一直没说话就进待机；唤醒后可回到本题续答
    followup_window_ms: 6000    # 续聊窗口：回合结束/播报完后免唤醒直接说话即新指令；0=关闭
  kws:                          # 本地 KWS 唤醒闸门（sherpa-onnx；见下「语音隐私边界」）
    enabled: true               # false = 关闭本地判定，每次人声段直接上云（最大召回）
    model_dir: "models/sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01"
    keywords_threshold: 0.25    # 检测阈值：越低越灵敏（漏报少、误报多）
    keywords_score: 1.0         # 关键词得分加成：越高越易命中
  call:                         # 通话模式（双击悬浮球进入，段落过三级判定漏斗）
    enabled: true
    open_window_s: 8            # 回答后免焦点追问窗口（秒）；0 关闭
    l0_min_rms: 0.02            # 段落能量低于此视为非人声（L0 粗筛）
    l0_min_seconds: 0.5         # 短于此的段本机丢弃（L0 粗筛）
    smart_turn_enabled: true    # Smart Turn v3「说完没」复核（L1）开关
    local_asr_model: "models/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20"
    merge_l2: true              # L2 合并调用：单次云端 chat 同时转写+四分类；false = 两步旧路径
  asr:                          # 在线 ASR（OpenAI 兼容；密钥在 config.secrets.yaml / 环境变量）
    active: openai              # KWS 命中后抬取指令文本；cloud 模式下兼做唤醒判定
    profiles:
      openai:
        provider: openai
        endpoint: ""            # 例: https://api.siliconflow.cn/v1
        model: ""               # 例: Qwen2-Audio-7B-Instruct
        language: "zh"
        timeout: 30
        chat_path: "/v1/chat/completions"
  tts:                          # 可选后端 TTS；默认浏览器 SpeechSynthesis
    enabled: false
    profiles:
      openai:
        provider: xiaomi        # 例：小米 MiMo 预置音色（model=mimo-v2.5-tts，voice 填音色名）
        endpoint: "https://api.xiaomimimo.com"
        model: "mimo-v2.5-tts"
        voice: "Chloe"          # 内置音色名；留空默认 mimo_default
        format: "wav"           # wav / mp3 / pcm16
        timeout: 30
```

### 语音隐私边界

唤醒判定默认在**本机**完成（`kws.*`，sherpa-onnx 关键词检测）：

- **没说唤醒词的音频被 KWS 在本机丢弃 —— 不出本机、不上云。** 只有命中唤醒词的那段才上传
  `asr.active` 指向的服务商抬取指令文本。`kws.enabled: false` 或 `cloud` 模式 = 旁路本地
  判定，每次人声段都上云（最大召回）。KWS 模型（`kws.model_dir`）缺失时自动旁路并在启动
  日志注明。
- `kws.keywords_threshold` 调灵敏度（越低越灵敏）；唤醒词本身在 `wake_word.keywords` 配，
  由 text2token 自动生成 KWS 关键词文件，改词无需手动编排。
- 降低调用量的其余旋钮：调大 `vad.min_speech_ms` 与 `vad.upload_throttle_ms`、调高
  `vad.silence_threshold`。代价是漏触发变多，反之亦然。
- 完整边界说明见 [Security.md](Security.md) 的「语音隐私边界」。

### call — 通话模式（三级判定漏斗）

双击悬浮球进入/退出通话模式：段落免唤醒直接过服务端三级漏斗（L0 规则 → L1 本地转写 →
L2 云端精判），命中进现有编排。字段：

| 字段 | 默认 | 说明 |
|---|---|---|
| `enabled` | `true` | 通话模式总开关 |
| `open_window_s` | `8` | 回答完成后的开放追问窗口（秒）：窗口内段落免 tab 焦点、漏斗放宽；`0` 关闭 |
| `l0_min_rms` | `0.02` | L0 能量底线：段落 RMS 低于此视为非人声，直接丢弃（可用真音频标定） |
| `l0_min_seconds` | `0.5` | L0 时长底线：短于此秒数的段直接丢弃 |
| `smart_turn_enabled` | `true` | L1 的 Smart Turn v3「说完没」复核开关（`pipecat-ai==1.12.0` 只用这一个组件） |
| `local_asr_model` | `models/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20` | L1 本地转写模型目录；**模型不入库**，用 `python scripts/fetch_local_asr_model.py` 幂等拉取 |
| `merge_l2` | `true` | L2 合并调用：单次云端 chat 同时精转写+四分类（省一次音频上传与一轮 LLM 判定）；只回文本时自动补判、失败自动回落两步旧路径；`false` = 直接走两步 |

**降级语义**（每一级「坏得静默、链路不断」）：

- **本地转写模型缺失/加载失败** → 跳过 L1，只走 L0+L2（功能可用、成本略升），记 warn
- **Smart Turn 加载失败** → 以浏览器 VAD 静音切段为回合边界（现状手感），记 warn
- **L2 云端 ASR/LLM 失败** → 该段按未命中静默丢弃 + audit 记 `call-funnel error`，不断链不弹错
- **漏斗误杀**：开放窗口内连续 miss 达阈值时对最后一段重跑 L2 且置 `relax`（宁可误报不可漏报）
- **审计口径**：命中走 `/api/voice/utter`；每级丢弃记 audit `call-funnel` 行；云端转写共用
  `audio-upload via=` 前缀（成本口径不变）

## server — 服务

```yaml
server:
  host: "127.0.0.1"
  port: 8520
  open_browser: true
  cors_origins: []              # 允许跨域来源（默认空 = 禁止跨域）
  resume_grace_s: 120           # SSE 断线宽限：断开后任务继续跑，/api/voice/resume 续播；0=断线即停
  # api_token 已移到 config.secrets.yaml（非 localhost 绑定时必须设置，否则拒绝启动）
```

## mcp — 外部 MCP server

```yaml
mcp:
  servers: []                   # 例: [{name: echo, command: py, args: ["-3.14", "scripts/mcp_echo_server.py"]}]
```

启动时自动连接并注册工具（`mcp_<server>_<tool>`）。

## rag — 检索索引

```yaml
rag:
  auto_index: true              # 启动时 index.db 缺失或源更新则自动重建；false 关闭
```

## memory — 长期记忆注入

```yaml
memory:
  recency_half_life_days: 30    # 新近度半衰期（天）
  recency_weight: 0.5           # 加权强度（0=关）
  inject_top_k: 5               # 注入条数上限
  inject_max_chars: 800         # 注入字符预算
  extract_recent_messages: 2    # 任务后提取回看的最近对话条数（用户/助手各 N）
```

## agent — 编排

```yaml
agent:
  recursion_limit: 12           # ReAct 步数上限
  multi_agent: false            # 复杂任务是否转多智能体协调者
  models_failover: []           # 主模型故障时依次尝试的备选模型（例: ["gpt-4o-mini", "qwen-turbo"]）
  structured_temperature: 0.2   # 意图/任务形成/提取等结构化输出阶段的温度
  auto_approve: false           # true=write/exec 自动放行不再询问（含子代理与技能；无人值守仍拒绝）
  confirm_timeout_s: 0          # 澄清/确认超时秒数，0=不限；到期按拒绝处理（fail-closed）
  condense_threshold_chars: 12000  # ReAct 历史滚动压缩阈值（字符），0=关闭
```

## llm_client — 重试 / 熔断

```yaml
llm_client:
  retry_max: 3
  retry_backoff_base: 0.5
  retry_backoff_max: 10.0
  circuit_breaker_threshold: 5   # 连续失败 N 次熔断
  circuit_breaker_cooldown: 30.0
  request_timeout: 60
```

## tools — 工具参数

```yaml
tools:
  search_max_results: 5         # web_search 最大结果数
  weather_timeout: 10
  llm_max_output_chars: 8000    # 喂给模型的工具正文截断（展示/落库口径独立不受影响）；0=不限
  lazy_groups: []               # 渐进式工具 schema：分组降级为一行简介（如 ["mcp"]），完整参数先调 tools_describe
```

## permissions — 工具权限策略

```yaml
permissions:
  default_action: allow         # 未命中任何规则时的兜底（默认也放行）
  tiers:
    read: allow                 # 三档默认全放行（2026-09-13 起）；改 ask 即恢复询问
    write: allow
    exec: allow
  rules: []                     # 形如 - {match: "run_*", action: deny}；deny 单调短路不可翻案
```

求值顺序：未注册工具 → 拒绝 > 任一 `deny` 规则短路 > 首条匹配规则 > 档位默认 > `default_action`。
与计划级确认共用同一份策略；设置页「设置 → 权限」可改，详见[安全模型](Security.md)。

## vendor_presets — 厂商目录扩展

`core/vendors.py` 内置目录之外，可在 `config.yaml` 追加 / 覆盖预设（设置页「新增 Profile」可见，
同 ID 覆盖内置）。endpoint 为基座 URL（不含 /v1），chat_path 与基座配对。

```yaml
vendor_presets:
  my-gateway:
    kind: llm                   # llm / asr / tts
    label: 我的网关
    provider: openai
    endpoint: "https://gateway.example.com"
    chat_path: "/v1/chat/completions"
    models: ["m1", "m2"]
    api_key_env: "MY_GATEWAY_KEY"
    compat: { stream_options: false }
```
