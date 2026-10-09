# -*- coding: utf-8 -*-
"配置 schema — voice 子模块（自 schema.py 拆出，纯移动）。"


from pydantic import BaseModel, ConfigDict, Field, model_validator

from .profiles import AsrSection, TtsSection

class WakeWordConfig(BaseModel):
    """唤醒词配置：开关、关键词（**可多个**）、灵敏度与模型路径。

    支持多个唤醒词，命中任意一个即唤醒。默认「衍衡」与「洛吉斯」（2026-09-13 改，此前是
    单一的「小逻小逻」）。

    `model_path` 是 Vosk 时代的遗留字段（浏览器端 WASM 模型 URL）。唤醒改走云端判定、Vosk
    引擎与模型都删除后前端已无人读它，默认值与前端 store / api schema 一样留空串；字段本身
    保留只是为了不破坏已有 `config.yaml`（本模型 `extra="forbid"`，删字段会让老配置启动即报错）。

    Wake-word config: enabled toggle, keywords (**plural**), sensitivity, and model path. Any one
    of the keywords wakes the engine. Defaults to 「衍衡」 and 「洛吉斯」 (changed 2026-09-13 from the
    single 「小逻小逻」).

    `model_path` is a leftover from the Vosk era (a browser-side WASM model URL). Since wake
    detection moved to the cloud and the Vosk engine and its model were deleted, nothing on the
    frontend reads it; the default is the empty string, matching the frontend store and the api
    schema. The field itself stays only so existing `config.yaml` files keep loading (`extra="forbid"`
    would make dropping it fail at startup).
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    keywords: list[str] = Field(default_factory=lambda: ["衍衡", "洛吉斯"])
    sensitivity: float = Field(0.5, ge=0.0, le=1.0)
    model_path: str = ""

    @model_validator(mode="before")
    @classmethod
    def _fold_legacy_keyword(cls, data):
        """把旧的单数 `keyword` 折进 `keywords`（老配置只写了一个词）。

        ⚠️ 这一步是为了**能启动**，不是洁癖：本模型是 `extra="forbid"`，直接删掉 `keyword`
        字段会让所有已有 `config.yaml` 在启动时抛 ValidationError。同时给出新旧两种写法时以
        `keywords` 为准，不合并。

        Folds a legacy singular `keyword` into `keywords`. This is about **booting**, not tidiness:
        the model is `extra="forbid"`, so dropping the `keyword` field outright would make every
        existing `config.yaml` raise at startup. When both forms are present `keywords` wins.

        Args:
            data: 原始输入。The raw input.

        Returns:
            归一化后的输入。The normalized input.
        """
        if isinstance(data, dict) and "keyword" in data:
            normalized = dict(data)
            legacy = normalized.pop("keyword")
            if legacy and not normalized.get("keywords"):
                normalized["keywords"] = [legacy]
            return normalized
        return data


class VadConfig(BaseModel):
    """语音活动检测（VAD）配置：静音阈值与时长上限。

    Voice activity detection (VAD) config: silence threshold and duration limits.
    """

    model_config = ConfigDict(extra="forbid")

    silence_threshold: float = Field(0.02, ge=0.0)
    silence_duration_ms: int = Field(1500, ge=0)
    max_duration_ms: int = Field(10000, ge=1000)
    # 裸唤醒后的等指令窗（毫秒）：只喊唤醒词不带指令时，窗内没说指令则作废。
    # 回答本身永不限时（取消限时回答），此键不再参与待答计时；键名保持 answer_timeout_ms
    # 以兼容旧 config.yaml 校验。
    # Post-bare-wake command window (ms): with only the wake word spoken, an instruction
    # not arriving inside the window voids it. Answers themselves are never timed out
    # (unlimited answer window); this key no longer times the answer wait. The name stays
    # answer_timeout_ms for old config.yaml compatibility. Lives here rather than in a new
    # section because it shares the family with max_duration_ms.
    answer_timeout_ms: int = Field(8000, gt=0)
    # 续聊窗口（docs/designs/03-A）：回合结束（done/error 且播报完）后的免唤醒窗口毫秒数，
    # 窗口内的语音段直接转写为新指令（不必喊唤醒词）；0=关闭（回到「done 后 3s 回聆听」旧行为）。
    # 放 vad 段因它与收听时序同族，且 editable_snapshot 只暴露 vad/wake_word 两个语音子段。
    # Follow-up window (docs/designs/03-A): wake-free window (ms) after a turn ends (done/
    # error, playback finished); segments inside are transcribed as fresh instructions (no
    # wake word). 0 disables (back to the legacy "3s after done → listening"). Lives in the
    # vad section (listening-timing family; editable_snapshot only exposes vad/wake_word).
    followup_window_ms: int = Field(6000, ge=0)
    # 唤醒上传的两道成本闸（子项目 1）：短于此长度的片段不上传（滤掉咳嗽/关门等爆音），
    # 两次上传之间的最小间隔（避免连续误触发时刷接口）。
    # Two cost gates for wake uploads: clips shorter than min_speech_ms are never uploaded
    # (filters coughs, door slams and other transients), and upload_throttle_ms sets the minimum
    # gap between uploads so a burst of false triggers cannot hammer the endpoint.
    min_speech_ms: int = Field(300, ge=0)
    upload_throttle_ms: int = Field(500, ge=0)
    # 打断播报（barge-in，docs/designs/02 批3）：助手播报期间不再整体静默，而是用一条
    # 独立的回声消除流做能量检测，连续超阈即掐断播报转入作答/指令分流。默认关 ——
    # 关闭时行为与旧版完全一致（播报期间停麦）。放在 vad 段是因为它与收听时序同族，
    # 且 editable_snapshot 只暴露 vad/wake_word 两个语音子段（放 voice 顶层前端收不到）。
    # Barge-in (docs/designs/02 batch 3): during playback the mic is not silenced
    # wholesale; a separate echo-cancelled stream runs energy detection and cuts the
    # playback on sustained speech, flowing into answer/command routing. Off by
    # default — when off, behaviour is identical to the old play-only-when-silent mode.
    # Lives in the vad section because it shares the listening-timing family and
    # editable_snapshot only exposes vad/wake_word (a voice-level key never reaches
    # the frontend).
    barge_in: bool = False  # default off: identical to the legacy listen-after-playback behaviour


class KwsConfig(BaseModel):
    """本地 KWS（关键词检测）前置闸门配置：sherpa-onnx zipformer-wenetspeech。

    KWS 在**云端 ASR 之前**本地判定音频里有没有唤醒词：未命中直接丢弃（背景媒体声/
    闲聊不上云、不花钱），命中才调 ASR 抬取指令文本。发音级检测（拼音 tokens），
    对「ASR 写什么字」免疫。

    本地前置闸门（keyword-spotting gate）configuration: sherpa-onnx
    zipformer-wenetspeech. KWS judges locally whether the audio contains a wake word
    **before** any cloud ASR call: misses are dropped outright (background media /
    chatter never leaves the machine or costs money), hits proceed to ASR for command
    extraction. Pronunciation-level detection (pinyin tokens), immune to "whatever
    ASR writes".
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    # 模型目录（tokens.txt + encoder/decoder/joiner onnx）；不存在时闸门自动禁用（不报错）。
    # Model dir (tokens.txt + encoder/decoder/joiner onnx); the gate auto-disables when absent.
    model_dir: str = "models/sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01"
    # 检测阈值：越低越灵敏（漏报少、误报多）。默认 0.25 是 sherpa 官方示例值。
    # Detection threshold: lower is more sensitive (fewer misses, more false hits).
    # 0.25 is the sherpa reference default.
    keywords_threshold: float = Field(0.25, ge=0.0, le=1.0)
    # 关键词得分加成：越高越易命中。Keyword score boost: higher hits more easily.
    keywords_score: float = Field(1.0, ge=0.0)


class CallConfig(BaseModel):
    """通话模式（免唤醒持续流转）配置：双击悬浮球进入，段落过三级判定漏斗。

    Call mode (wake-free continuous flow) config: entered by double-clicking the float
    ball; each VAD segment runs the three-stage judgement funnel (L0 rules → L1 local
    transcription/turn → L2 cloud gate). `local_asr_model` missing/unloadable degrades
    the funnel to L0+L2 (never blocks the mode); `smart_turn_enabled=False` degrades to
    VAD-cut-as-turn-boundary (the legacy behaviour).
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    # 开放窗口（秒）：回答完成后免焦点追问的时限；0 关闭。
    # Open window (seconds): focus-free follow-up window after a reply; 0 disables.
    open_window_s: float = Field(8.0, ge=0.0)
    # L0 能量与时长底线：低于此的段视为非人声/清嗓，本机丢弃。
    # L0 energy/duration floor: segments below are non-speech (cleared throat), dropped locally.
    l0_min_rms: float = Field(0.02, ge=0.0, le=1.0)
    l0_min_seconds: float = Field(0.5, ge=0.0)
    # Smart Turn（说完没复核）开关：关=以浏览器 VAD 静音切段为回合边界（旧行为）。
    # Smart Turn switch: off = browser VAD cut is the turn boundary (legacy behaviour).
    smart_turn_enabled: bool = True
    # 本地流式转写模型目录；缺失时跳过 L1，只走 L0+L2。
    # Local streaming ASR model dir; when missing, skip L1 and run L0+L2 only.
    local_asr_model: str = "models/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20"
    # L2 合并调用：单次云端 chat 同时精转写+四分类（省一次上传与一轮 LLM）；
    # False = 回到两步（cloud_transcribe + judge）。合并失败也自动回落两步。
    # L2 merged call: one cloud chat does ASR + four-way judge (saves one upload and
    # one LLM round); False = legacy two-step (cloud_transcribe + judge). A failed
    # merged call falls back to the two-step automatically.
    merge_l2: bool = True
    # 通话会话无段落自动过期秒数（防会话泄漏；此前是 call.py 硬编码 _SESSION_TTL_S）。
    # Idle expiry of a call session in seconds (leak guard; formerly the hardcoded
    # _SESSION_TTL_S in call.py).
    session_ttl_s: float = Field(300.0, gt=0)
    # 开放窗口内连续 miss 数，达到后 L2 复判放宽（此前是 call.py 硬编码 _RELAX_AFTER）。
    # Consecutive misses inside the open window before the L2 re-judge relaxes
    # (formerly the hardcoded _RELAX_AFTER in call.py).
    relax_after_misses: int = Field(2, ge=1)


class VoiceSection(BaseModel):
    """语音段配置：唤醒词、VAD、KWS、ASR 与 TTS 子配置。

    Voice section config: wake-word, VAD, KWS, ASR, and TTS sub-configs.
    """

    model_config = ConfigDict(extra="forbid")

    wake_word: WakeWordConfig = Field(default_factory=lambda: WakeWordConfig())
    vad: VadConfig = Field(default_factory=lambda: VadConfig())
    kws: KwsConfig = Field(default_factory=lambda: KwsConfig())
    call: CallConfig = Field(default_factory=lambda: CallConfig())
    asr: AsrSection = Field(default_factory=lambda: AsrSection())
    tts: TtsSection = Field(default_factory=lambda: TtsSection())
