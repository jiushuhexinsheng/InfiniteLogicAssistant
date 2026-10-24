# -*- coding: utf-8 -*-
"""唤醒 / VAD / 配置状态响应。Wake-word, VAD and config-status responses."""
from typing import Any, Literal

from pydantic import BaseModel, Field

from .base import ApiResponse

class WakeWordConfig(BaseModel):
    """唤醒词配置（**可多个**）。

    ⚠️ 本类是 `core/config/schema.py` 里 WakeWordConfig 的**手工副本**（两处定义必须同步）：
    FastAPI 的 response_model 会在序列化时**丢掉响应里多余字段**，故只改配置模型而不同步这里，
    新增字段会被静默过滤掉、前端收不到（`VadConfig` 那次就是这么踩的）。

    Wake-word detection configuration (plural keywords).

    NOTE: this is a hand-maintained **duplicate** of the WakeWordConfig in
    `core/config/schema.py`; the two must be kept in sync. FastAPI's response_model drops extra
    fields during serialization, so changing only the config model would silently filter the field
    out and the frontend would never see it (exactly how `VadConfig` was broken before).

    `model_path` 是 Vosk 时代的遗留字段，唤醒改走云端判定后前后端都无人读它，默认空串 ——
    与 `core/config/schema.py` 的同名字段保持一致。

    `model_path` is a leftover from the Vosk era; nothing reads it now that wake detection runs in
    the cloud, so its default is the empty string — kept identical to the same field in
    `core/config/schema.py`.
    """
    enabled: bool = True
    # 默认值必须与 `core/config/schema.py` 一致：本模型在 `EditableSnapshot` 里，设置页会把整个
    # 对象原样 PATCH 回来 —— 默认值漂移不只是「前端读不到」，而是**下一次保存设置时把漂移值
    # 写回 config.yaml**。用例 `test_wake_and_vad_duplicates_in_api_schemas_stay_in_sync` 钉住这点。
    #
    # ⚠️ 这里写 list 字面量而不是 `default_factory`：pydantic 不会把工厂的返回值放进 JSON schema
    # 的 `default`，于是 openapi-typescript 会把这个字段生成为**可选**（`keywords?`），
    # 白白改掉响应契约。pydantic v2 对可变默认值逐实例深拷贝，字面量是安全的。
    #
    # The default must match `core/config/schema.py`: this model sits inside `EditableSnapshot`,
    # which the settings page round-trips wholesale, so a drift is not merely "the frontend cannot
    # read it" — it gets written back into config.yaml on the next settings save. The
    # duplicate-model guard pins this down.
    #
    # NOTE: a list literal rather than `default_factory`: pydantic does not put a factory's return
    # value into the JSON schema's `default`, so openapi-typescript would emit the field as
    # **optional** (`keywords?`) and quietly change the response contract. pydantic v2 deep-copies
    # mutable defaults per instance, so the literal is safe.
    keywords: list[str] = Field(default=["衍衡", "洛吉斯"])
    sensitivity: float = 0.5
    model_path: str = ""

class VadConfig(BaseModel):
    """VAD（语音活动检测）配置。

    ⚠️ 本类是 `core/config/schema.py` 里 VadConfig 的**手工副本**（两处定义必须同步）：
    FastAPI 的 response_model 会在序列化时**丢掉响应里多余字段**，故只改配置模型
    而不同步这里，新增字段会被静默过滤掉、前端收不到。

    VAD (Voice Activity Detection) configuration.

    NOTE: this is a hand-maintained **duplicate** of the VadConfig in
    `core/config/schema.py`; the two must be kept in sync. FastAPI's response_model drops
    extra fields during serialization, so adding a field only to the config model would be
    silently filtered out and never reach the frontend.
    """
    # ── 本地 VAD（流式链路；见 config/schema/voice.py 同名字段）──
    mode: Literal["local", "off"] = "local"
    engine: Literal["ten-vad", "silero"] = "ten-vad"
    model: str = "models/vad/ten-vad.onnx"
    vad_threshold: float = 0.5
    window_size: int = 0
    provider: Literal["cpu", "cuda", "coreml"] = "cpu"
    device: int = 0
    num_threads: int = 0
    params: dict[str, dict[str, Any]] = Field(default_factory=dict)

    silence_threshold: float = 0.02
    silence_duration_ms: int = 1500
    max_duration_ms: int = 10000
    # 裸唤醒后的等指令窗（毫秒）；回答本身永不限时（键名保持 answer_timeout_ms 兼容旧配置）。
    # Post-bare-wake command window (ms); answers themselves are never timed out (key name
    # kept as answer_timeout_ms for old-config compatibility).
    answer_timeout_ms: int = 8000
    min_speech_ms: int = 300
    upload_throttle_ms: int = 500
    # 续聊窗口（毫秒，0=关闭）：见 config/schema.py 同名字段（两处必须同步）。
    # Follow-up window (ms, 0 = off): see the same field in config/schema.py (keep in sync).
    followup_window_ms: int = 6000
    # 聆听空闲超时（秒，0=永不）：见 config/schema/voice.py 同名字段（两处必须同步）。
    # Listening idle timeout (s, 0 = never): same field in config/schema/voice.py (keep in sync).
    listen_idle_s: int = 180
    # 打断播报（barge-in）开关：见 config/schema.py 同名字段（两处必须同步）。
    # Barge-in toggle: see the same field in config/schema.py (both must stay in sync).
    barge_in: bool = False

class CallConfig(BaseModel):
    """通话模式配置（`core/config/schema.py` 里 CallConfig 的**手工副本**，两处必须同步，
    理由同 WakeWordConfig/VadConfig：response_model 会静默过滤未声明字段）。

    Call-mode configuration (hand-maintained duplicate of CallConfig in
    `core/config/schema.py`; the two must stay in sync — response_model silently drops
    undeclared fields, same trap as WakeWordConfig/VadConfig).
    """
    enabled: bool = True
    open_window_s: float = 8.0
    l0_min_rms: float = 0.02
    l0_min_seconds: float = 0.5
    local_asr_model: str = "models/asr/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20"
    # 会话过期 / miss 放宽阈值：见 config/schema/voice.py 同名字段（两处必须同步）。
    # Session expiry / miss-relax threshold: same fields in config/schema/voice.py (keep in sync).
    session_ttl_s: float = 300.0
    relax_after_misses: int = 2

class StreamingConfig(BaseModel):
    """流式语音会话配置（config/schema/voice.py 副本，两处必须同步）。

    Streaming voice-session config (copy of config/schema/voice.py; keep in sync).
    """

    enabled: bool = True
    partial_interval_ms: int = 120
    endpoint_silence_ms: int = 700
    max_utterance_ms: int = 15000


class HardwareConfig(BaseModel):
    """浏览器侧硬件选项（config/schema/voice.py 副本，两处必须同步）。

    Browser-side hardware options (copy of config/schema/voice.py; keep in sync).
    """

    input_device: str = ""
    output_device: str = ""
    echo_cancellation: bool = True
    noise_suppression: bool = True
    auto_gain: bool = True


class KwsConfig(BaseModel):
    """本地 KWS 配置（config/schema/voice.py 副本，两处必须同步）。

    Local KWS config (copy of config/schema/voice.py; keep in sync).
    """

    enabled: bool = True
    mode: Literal["local", "api", "off"] = "local"
    model_dir: str = "models/kws/sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01"
    provider: Literal["cpu", "cuda", "coreml"] = "cpu"
    device: int = 0
    num_threads: int = 2
    params: dict[str, dict[str, Any]] = Field(default_factory=dict)
    keywords_threshold: float = 0.25
    keywords_score: float = 1.0


class ConfigResponse(ApiResponse):
    """配置状态端点响应（LLM/ASR/TTS 可用性、唤醒词、VAD）。

    ``/api/config`` status response (LLM/ASR/TTS availability, wake word, VAD).
    """
    llm_available: bool = False
    llm_profile: str = ""
    # 当前模型名：同一供应商内切换模型时 llm_profile 不变，顶栏需要它。
    # Current model name: llm_profile stays the same when switching models inside one
    # provider, so the header needs this field.
    llm_model: str = ""
    asr_available: bool = False
    asr_profile: str = ""
    tts_available: bool = False
    tts_profile: str = ""
    tts_voice: str | None = None
    tts_model: str | None = None
    wake_word: WakeWordConfig
    vad: VadConfig
    call: CallConfig
    # 能力模式（前端据此选择流式链路/本地/API 展示；见 voice.asr/vad/kws/tts）。
    # Capability modes (the frontend chooses the streaming path and local/API labels).
    streaming: bool = True
    asr_mode: str = "cloud"
    vad_mode: str = "local"
    kws_mode: str = "local"
    tts_mode: str = "api"
    hardware: dict[str, Any] = {}

class CallSessionResponse(ApiResponse):
    """通话会话 start/stop 响应。Call session start/stop response."""

    open_window_s: float = 0.0


class CallSegmentResponse(ApiResponse):
    """通话段落漏斗响应。Call segment funnel response.

    hit=True 才把 text 当指令送编排；stage/reason 供 audit 对照（前端不读）。
    """

    hit: bool = False
    text: str = ""
    stage: str = ""
    reason: str = ""

class UploadStatsResponse(ApiResponse):
    """语音上传成本统计（P2-6 成本仪表）：三前缀计数 + 近 7 日趋势。

    **只回计数与日期**——audit 行含转写原文，绝不回放（见 stats.py 安全口径）。

    Voice upload cost stats (P2-6 cost dashboard): per-via counts + 7-day trend.
    Counts and dates only — audit lines carry raw transcripts and are never echoed.
    """

    total: int = 0
    by_via: dict[str, int] = {}
    days: list[dict] = []
