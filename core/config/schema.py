# -*- coding: utf-8 -*-
"""配置 schema — pydantic 强类型模型（纯定义，无 IO / 无全局状态）

加载时经 pydantic 模型校验（类型 / 范围 / 枚举，写错配置启动即报错）。
结构对应 config.yaml：llm / voice / server / mcp / rag / agent / llm_client / tools + vendor_presets。
"""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CompatConfig(BaseModel):
    """厂商兼容开关（影响请求体组装；默认与既有行为一致，纯增量）。"""

    model_config = ConfigDict(extra="allow")

    stream_options: bool = True   # 是否发 stream_options.include_usage（部分网关拒绝未知字段）
    max_tokens_field: Literal["max_tokens", "max_completion_tokens"] = "max_tokens"


class VendorPreset(BaseModel):
    """厂商目录预设（代码内置 + config.yaml vendor_presets 扩展）；extra=forbid 防拼错键。"""

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
    """各 profile 公共字段；extra=allow 保留用户透传键（如 TTS 的 format/voice_ref）。"""

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
    model: str = ""
    vision_model: str = ""
    max_tokens: int = Field(4096, gt=0)
    temperature: float = Field(0.7, ge=0.0, le=2.0)


class AsrProfile(ProfileBase):
    model: str = ""
    language: str = "zh"


class TtsProfile(ProfileBase):
    model: str = "tts-1"
    voice: str = "alloy"
    format: Literal["wav", "mp3", "pcm16"] = "wav"
    voice_ref: str | None = None
    voices: list[str] = Field(default_factory=list)   # 音色列表（UI 下拉）


class LlmSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active: str = "deepseek"
    profiles: dict[str, LlmProfile] = Field(default_factory=dict)


class AsrSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active: str = "openai"
    profiles: dict[str, AsrProfile] = Field(default_factory=dict)


class TtsSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    active: str = "openai"
    profiles: dict[str, TtsProfile] = Field(default_factory=dict)


class WakeWordConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    keyword: str = "小逻小逻"
    sensitivity: float = Field(0.5, ge=0.0, le=1.0)
    model_path: str = "/models/vosk-model-small-cn-0.22.tar.gz"


class VadConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    silence_threshold: float = Field(0.02, ge=0.0)
    silence_duration_ms: int = Field(1500, ge=0)
    max_duration_ms: int = Field(10000, ge=1000)


class VoiceSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wake_word: WakeWordConfig = Field(default_factory=lambda: WakeWordConfig())
    vad: VadConfig = Field(default_factory=lambda: VadConfig())
    asr: AsrSection = Field(default_factory=lambda: AsrSection())
    tts: TtsSection = Field(default_factory=lambda: TtsSection())


class AgentSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recursion_limit: int = Field(12, gt=0)
    multi_agent: bool = False
    models_failover: list[str] = Field(default_factory=list)  # 主模型故障时的备选模型


class LlmClientSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retry_max: int = Field(3, ge=0)
    retry_backoff_base: float = Field(0.5, gt=0)
    retry_backoff_max: float = Field(10.0, gt=0)
    circuit_breaker_threshold: int = Field(5, gt=0)
    circuit_breaker_cooldown: float = Field(30.0, gt=0)
    request_timeout: int = Field(60, gt=0)


class ToolsSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    search_max_results: int = Field(5, gt=0)
    weather_timeout: int = Field(10, gt=0)


class McpServer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    command: str
    args: list[str] = Field(default_factory=list)


class McpSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    servers: list[McpServer] = Field(default_factory=list)


class RagSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auto_index: bool = True


class ServerSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = "127.0.0.1"
    port: int = Field(8520, ge=1, le=65535)
    open_browser: bool = True
    api_token: str = ""  # 由 loader 从 secrets/环境注入
    cors_origins: list[str] = Field(default_factory=list)


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm: LlmSection = Field(default_factory=lambda: LlmSection())
    voice: VoiceSection = Field(default_factory=lambda: VoiceSection())
    server: ServerSection = Field(default_factory=lambda: ServerSection())
    mcp: McpSection = Field(default_factory=lambda: McpSection())
    rag: RagSection = Field(default_factory=lambda: RagSection())
    agent: AgentSection = Field(default_factory=lambda: AgentSection())
    llm_client: LlmClientSection = Field(default_factory=lambda: LlmClientSection())
    tools: ToolsSection = Field(default_factory=lambda: ToolsSection())
    vendor_presets: dict[str, VendorPreset] = Field(default_factory=dict)  # 厂商目录 YAML 扩展
