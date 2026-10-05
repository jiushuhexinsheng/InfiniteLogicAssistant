# -*- coding: utf-8 -*-
"""唤醒 / VAD / 配置状态响应。Wake-word, VAD and config-status responses."""
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
    silence_threshold: float = 0.02
    silence_duration_ms: int = 1500
    max_duration_ms: int = 10000
    # 等待操作者语音回答的静音超时（毫秒）。
    # Silence timeout (ms) while waiting for a spoken answer.
    answer_timeout_ms: int = 8000
    min_speech_ms: int = 300
    upload_throttle_ms: int = 500
    # 续聊窗口（毫秒，0=关闭）：见 config/schema.py 同名字段（两处必须同步）。
    # Follow-up window (ms, 0 = off): see the same field in config/schema.py (keep in sync).
    followup_window_ms: int = 6000
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
    smart_turn_enabled: bool = True
    local_asr_model: str = "models/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20"

class ConfigResponse(ApiResponse):
    """配置状态端点响应（LLM/ASR/TTS 可用性、唤醒词、VAD）。

    ``/api/config`` status response (LLM/ASR/TTS availability, wake word, VAD).
    """
    llm_available: bool = False
    llm_profile: str = ""
    asr_available: bool = False
    asr_profile: str = ""
    tts_available: bool = False
    tts_profile: str = ""
    tts_voice: str | None = None
    tts_model: str | None = None
    wake_word: WakeWordConfig
    vad: VadConfig
    call: CallConfig

class WakeResponse(ApiResponse):
    """唤醒检测响应。

    text 是**原始**转写（不被归一化改写），matched 为是否命中，command 为唤醒词之后的内容
    （仅唤醒词时为空串）。

    Wake-detection response. text is the **raw** transcript, matched says whether a wake word hit,
    and command is what followed it (empty when only the wake word was spoken).
    """

    matched: bool = False
    command: str = ""
    text: str = ""

class WakeCheckResponse(ApiResponse):
    """本地 KWS 快检响应（`POST /voice/wake/check`）。

    只做「有没有唤醒词」的本地判定（毫秒级、不出本机、不调云端 ASR）：
    hit=True 命中；hit=False 未命中（调用方丢弃该段）；bypass=True 闸门不可用
    （模型缺失/解析失败），调用方应回退完整 /voice/wake 路径而不是丢唤醒。

    Local KWS quick-check response. Only the local "is the wake word present"
    verdict (milliseconds, no cloud ASR): hit=True means yes; hit=False means drop
    the clip; bypass=True means the gate is unavailable (model missing / parse
    failure) and the caller should fall back to the full /voice/wake path rather
    than lose the wake.
    """

    hit: bool = False
    bypass: bool = False

