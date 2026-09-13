# -*- coding: utf-8 -*-
"""配置 schema — pydantic 强类型模型（纯定义，无 IO / 无全局状态）

Configuration schema — pydantic strongly-typed models (pure definitions, no IO / no global state).

加载时经 pydantic 模型校验（类型 / 范围 / 枚举，写错配置启动即报错）。
结构对应 config.yaml：llm / voice / server / mcp / rag / agent / llm_client / tools + vendor_presets。

Validated by pydantic models on load (types / ranges / enums; a bad config fails fast at startup).
Structure mirrors config.yaml: llm / voice / server / mcp / rag / agent / llm_client / tools + vendor_presets.
"""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CompatConfig(BaseModel):
    """厂商兼容开关（影响请求体组装；默认与既有行为一致，纯增量）。

    Vendor compatibility toggles (affect request-body assembly; defaults preserve existing
    behavior, purely additive).
    """

    model_config = ConfigDict(extra="allow")

    stream_options: bool = True   # 是否发 stream_options.include_usage（部分网关拒绝未知字段）
    max_tokens_field: Literal["max_tokens", "max_completion_tokens"] = "max_tokens"


class VendorPreset(BaseModel):
    """厂商目录预设（代码内置 + config.yaml vendor_presets 扩展）；extra=forbid 防拼错键。

    Vendor catalog preset (built into the code + config.yaml vendor_presets extension);
    extra=forbid prevents typos in keys.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["llm", "asr", "tts"]
    label: str = ""
    provider: str = "openai"   # 协议：openai / anthropic / gemini
    endpoint: str = ""         # 基座 URL（不含 /v1，与 chat_path 配对）
    chat_path: str = ""
    models_path: str = ""      # 获取模型列表路径；空则从 chat_path 推导
    models: list[str] = Field(default_factory=list)
    vision_models: list[str] = Field(default_factory=list)
    voices: list[str] = Field(default_factory=list)   # 仅 TTS
    api_key_env: str = ""      # 推荐环境变量名（非密钥本身）
    compat: dict[str, Any] = Field(default_factory=dict)
    defaults: dict[str, Any] = Field(default_factory=dict)


class ProfileBase(BaseModel):
    """各 profile 公共字段；extra=allow 保留用户透传键（如 TTS 的 format/voice_ref）。

    Common fields shared by all profiles; extra=allow keeps user pass-through keys
    (e.g. TTS format/voice_ref).
    """

    model_config = ConfigDict(extra="allow")

    provider: str = "openai"   # 协议：openai / anthropic / gemini（LLM 分派用）
    vendor: str = ""           # 厂商目录 ID（UI 元数据，不参与请求）
    endpoint: str = ""
    api_key: str = ""  # 由 loader 从 secrets/环境注入；config.yaml 不写
    api_key_env: str = ""      # 本 profile 专用环境变量名（优先级最高）
    chat_path: str = "/v1/chat/completions"
    timeout: int = Field(30, gt=0)
    models: list[str] = Field(default_factory=list)   # 可用模型列表（UI 下拉 / 展示）
    models_path: str = ""      # 获取模型列表路径；空则从 chat_path 推导
    compat: CompatConfig = Field(default_factory=CompatConfig)


class LlmProfile(ProfileBase):
    """LLM profile：模型名、视觉模型与生成参数（max_tokens / temperature）。

    LLM profile: model name, vision model, and generation parameters (max_tokens / temperature).
    """

    model: str = ""
    vision_model: str = ""
    max_tokens: int = Field(4096, gt=0)
    temperature: float = Field(0.7, ge=0.0, le=2.0)


class AsrProfile(ProfileBase):
    """ASR profile：语音识别模型与识别语言。

    ASR profile: speech-recognition model and recognition language.
    """

    model: str = ""
    language: str = "zh"


class TtsProfile(ProfileBase):
    """TTS profile：语音合成模型、音色与输出格式。

    TTS profile: speech-synthesis model, voice, and output format.
    """

    model: str = "tts-1"
    voice: str = "alloy"
    format: Literal["wav", "mp3", "pcm16"] = "wav"
    voice_ref: str | None = None
    voices: list[str] = Field(default_factory=list)   # 音色列表（UI 下拉）


class LlmSection(BaseModel):
    """LLM 段配置：当前激活 profile 及全部命名 profile。

    LLM section config: the active profile and all named profiles.
    """

    model_config = ConfigDict(extra="forbid")

    active: str = "deepseek"
    profiles: dict[str, LlmProfile] = Field(default_factory=dict)


class AsrSection(BaseModel):
    """ASR 段配置：当前激活 profile 及全部命名 profile。

    ASR section config: the active profile and all named profiles.
    """

    model_config = ConfigDict(extra="forbid")

    active: str = "openai"
    profiles: dict[str, AsrProfile] = Field(default_factory=dict)


class TtsSection(BaseModel):
    """TTS 段配置：启用开关、当前激活 profile 及全部命名 profile。

    TTS section config: enabled toggle, the active profile, and all named profiles.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    active: str = "openai"
    profiles: dict[str, TtsProfile] = Field(default_factory=dict)


class WakeWordConfig(BaseModel):
    """唤醒词配置：开关、关键词、灵敏度与模型路径。

    Wake-word config: enabled toggle, keyword, sensitivity, and model path.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    keyword: str = "小逻小逻"
    sensitivity: float = Field(0.5, ge=0.0, le=1.0)
    model_path: str = "/models/vosk-model-small-cn-0.22.tar.gz"


class VadConfig(BaseModel):
    """语音活动检测（VAD）配置：静音阈值与时长上限。

    Voice activity detection (VAD) config: silence threshold and duration limits.
    """

    model_config = ConfigDict(extra="forbid")

    silence_threshold: float = Field(0.02, ge=0.0)
    silence_duration_ms: int = Field(1500, ge=0)
    max_duration_ms: int = Field(10000, ge=1000)
    # 等待操作者语音回答的静音超时（毫秒）：超时无语音则进入待机（引擎仍听唤醒词）。
    # 与 max_duration_ms 同族（都是收听时序），故放在本段而非新增分段。
    # Silence timeout (ms) while waiting for a spoken answer; on timeout the assistant
    # enters standby (the engine still listens for the wake word). It lives here rather
    # than in a new section because it shares the family with max_duration_ms.
    answer_timeout_ms: int = Field(8000, gt=0)


class VoiceSection(BaseModel):
    """语音段配置：唤醒词、VAD、ASR 与 TTS 子配置。

    Voice section config: wake-word, VAD, ASR, and TTS sub-configs.
    """

    model_config = ConfigDict(extra="forbid")

    wake_word: WakeWordConfig = Field(default_factory=lambda: WakeWordConfig())
    vad: VadConfig = Field(default_factory=lambda: VadConfig())
    asr: AsrSection = Field(default_factory=lambda: AsrSection())
    tts: TtsSection = Field(default_factory=lambda: TtsSection())


class AgentSection(BaseModel):
    """Agent 段配置：递归上限、多智能体开关与结构化输出温度。

    Agent section config: recursion limit, multi-agent toggle, and structured-output temperature.
    """

    model_config = ConfigDict(extra="forbid")

    recursion_limit: int = Field(12, gt=0)
    multi_agent: bool = False
    models_failover: list[str] = Field(default_factory=list)  # 主模型故障时的备选模型
    # 结构化输出阶段（意图/任务形成/拆解/事实提取）的温度，单独调低以稳定 JSON 输出
    structured_temperature: float = Field(0.2, ge=0.0, le=2.0)


class LlmClientSection(BaseModel):
    """LLM 客户端段配置：重试、熔断与请求超时参数。

    LLM client section config: retry, circuit-breaker, and request-timeout parameters.
    """

    model_config = ConfigDict(extra="forbid")

    retry_max: int = Field(3, ge=0)
    retry_backoff_base: float = Field(0.5, gt=0)
    retry_backoff_max: float = Field(10.0, gt=0)
    circuit_breaker_threshold: int = Field(5, gt=0)
    circuit_breaker_cooldown: float = Field(30.0, gt=0)
    request_timeout: int = Field(60, gt=0)


class ToolsSection(BaseModel):
    """工具段配置：搜索与天气等外部工具参数。

    Tools section config: parameters for external tools such as search and weather.
    """

    model_config = ConfigDict(extra="forbid")

    search_max_results: int = Field(5, gt=0)
    weather_timeout: int = Field(10, gt=0)


class PermissionRule(BaseModel):
    """一条权限规则：match 为工具名或 glob（fnmatch 语义，大小写敏感）。

    A permission rule: match is a tool name or a glob (fnmatch semantics, case-sensitive).
    """

    model_config = ConfigDict(extra="forbid")

    match: str
    action: Literal["allow", "ask", "deny"]


class PermissionTiers(BaseModel):
    """按工具风险层级设的默认动作。Per-tier default action, keyed by tool risk."""

    model_config = ConfigDict(extra="forbid")

    read: Literal["allow", "ask", "deny"] = "allow"
    write: Literal["allow", "ask", "deny"] = "ask"
    exec: Literal["allow", "ask", "deny"] = "ask"


class PermissionsSection(BaseModel):
    """工具权限策略：层级默认 + 规则覆盖。

    默认值等价于改造前的行为（read 免询问、write/exec 询问），故既有配置文件
    无 permissions 段时行为不变。

    Tool permission policy: per-tier defaults plus rule overrides. The defaults match
    the pre-change behaviour (read auto-allowed, write/exec asked), so an existing
    config without a permissions section behaves unchanged.
    """

    model_config = ConfigDict(extra="forbid")

    default_action: Literal["allow", "ask", "deny"] = "ask"
    tiers: PermissionTiers = Field(default_factory=lambda: PermissionTiers())
    rules: list[PermissionRule] = Field(default_factory=list)


class McpServer(BaseModel):
    """MCP 服务器条目：名称、启动命令与参数。

    MCP server entry: name, launch command, and arguments.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    command: str
    args: list[str] = Field(default_factory=list)


class McpSection(BaseModel):
    """MCP 段配置：服务器列表。

    MCP section config: the server list.
    """

    model_config = ConfigDict(extra="forbid")

    servers: list[McpServer] = Field(default_factory=list)


class RagSection(BaseModel):
    """RAG 段配置：自动索引开关。

    RAG section config: auto-index toggle.
    """

    model_config = ConfigDict(extra="forbid")

    auto_index: bool = True


class ServerSection(BaseModel):
    """服务器段配置：监听地址、端口、自动开浏览器与 API Token。

    Server section config: listen host, port, auto-open browser, and API token.
    """

    model_config = ConfigDict(extra="forbid")

    host: str = "127.0.0.1"
    port: int = Field(8520, ge=1, le=65535)
    open_browser: bool = True
    api_token: str = ""  # 由 loader 从 secrets/环境注入
    cors_origins: list[str] = Field(default_factory=list)


class Settings(BaseModel):
    """顶层配置模型：汇总 llm / voice / server / mcp / rag / agent / llm_client / tools / vendor_presets。

    Top-level configuration model: aggregates llm / voice / server / mcp / rag / agent /
    llm_client / tools / vendor_presets.
    """

    model_config = ConfigDict(extra="forbid")

    llm: LlmSection = Field(default_factory=lambda: LlmSection())
    voice: VoiceSection = Field(default_factory=lambda: VoiceSection())
    server: ServerSection = Field(default_factory=lambda: ServerSection())
    mcp: McpSection = Field(default_factory=lambda: McpSection())
    rag: RagSection = Field(default_factory=lambda: RagSection())
    agent: AgentSection = Field(default_factory=lambda: AgentSection())
    llm_client: LlmClientSection = Field(default_factory=lambda: LlmClientSection())
    tools: ToolsSection = Field(default_factory=lambda: ToolsSection())
    permissions: PermissionsSection = Field(default_factory=lambda: PermissionsSection())
    vendor_presets: dict[str, VendorPreset] = Field(default_factory=dict)  # 厂商目录 YAML 扩展
