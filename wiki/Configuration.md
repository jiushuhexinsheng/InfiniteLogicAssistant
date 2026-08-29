# 配置说明

配置采用 **pydantic 强类型校验 + 双文件分离**（非敏感配置 / 密钥独立存储），
加载实现位于 `core/config/` 包（`loader.py` 读取 + `schema.py` 模型校验）。

## 三个配置源（优先级从低到高）

| 源 | 内容 | 说明 |
|---|---|---|
| `config.yaml` | 非敏感结构（llm / voice / server / mcp / rag / agent / llm_client / tools / vendor_presets） | 由 `config.yaml.example` 复制；经 pydantic 校验，类型 / 范围 / 枚举写错启动即报错 |
| `config.secrets.yaml` | 密钥（`llm/asr/tts.api_key`、`server.api_token`、`profiles.<name>` 每 profile 密钥） | 由 `config.secrets.yaml.example` 复制；**gitignored，不入库** |
| 环境变量 | `LLM_API_KEY` / `ASR_API_KEY` / `TTS_API_KEY` / `SERVER_API_TOKEN` | 优先级最高，覆盖 secrets 文件 |

**单 profile 密钥解析优先级**：`profile.api_key_env` 指向的环境变量 > 段全局环境变量 >
`secrets.profiles[name]` > secrets 段默认 `api_key` > 旧 `config.yaml` 内联 `api_key`（弃用，仅迁移）。

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

内置厂商目录（`core/providers.py`）：deepseek / openai / qwen / glm / kimi / doubao / qianfan /
xinghuo / minimax / siliconflow / openrouter / ollama / lmstudio / anthropic / gemini / xiaomi-mimo。
设置页「新增 Profile」可从目录一键预填；`config.yaml` 的 `vendor_presets` 可追加 / 覆盖自定义厂商。

## voice — 语音

```yaml
voice:
  wake_word:
    enabled: true
    keyword: "小逻小逻"           # 浏览器端 Vosk WASM 唤醒词
    sensitivity: 0.5
    model_path: "/models/vosk-model-small-cn-0.22.tar.gz"   # 浏览器端 URL
  vad:                          # 静音检测（自动停止录音）
    silence_threshold: 0.02
    silence_duration_ms: 1500
    max_duration_ms: 10000
  asr:                          # 在线 ASR（OpenAI 兼容；密钥在 config.secrets.yaml / 环境变量）
    active: openai
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

## server — 服务

```yaml
server:
  host: "127.0.0.1"
  port: 8520
  open_browser: true
  cors_origins: []              # 允许跨域来源（默认空 = 禁止跨域）
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

## agent — 编排

```yaml
agent:
  recursion_limit: 12           # ReAct 步数上限
  multi_agent: false            # 复杂任务是否转多智能体协调者
  models_failover: []           # 主模型故障时依次尝试的备选模型（例: ["gpt-4o-mini", "qwen-turbo"]）
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
```

## vendor_presets — 厂商目录扩展

`core/providers.py` 内置目录之外，可在 `config.yaml` 追加 / 覆盖预设（设置页「新增 Profile」可见，
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
