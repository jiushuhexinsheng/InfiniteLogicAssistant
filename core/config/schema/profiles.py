# -*- coding: utf-8 -*-
"""配置 schema — profiles 子模块（自 schema.py 拆出，纯移动）。

LLM/ASR/TTS profile 与对应 section；VendorPreset/CompatConfig 供顶层 Settings 使用。
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
