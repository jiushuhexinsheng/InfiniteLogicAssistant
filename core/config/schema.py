# -*- coding: utf-8 -*-
"""配置 schema — pydantic 强类型模型（纯定义，无 IO / 无全局状态）

Configuration schema — pydantic strongly-typed models (pure definitions, no IO / no global state).

加载时经 pydantic 模型校验（类型 / 范围 / 枚举，写错配置启动即报错）。
结构对应 config.yaml：llm / voice / server / mcp / rag / agent / llm_client / tools + vendor_presets。

Validated by pydantic models on load (types / ranges / enums; a bad config fails fast at startup).
Structure mirrors config.yaml: llm / voice / server / mcp / rag / agent / llm_client / tools + vendor_presets.
"""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    # 等待操作者语音回答的静音超时（毫秒）：超时无语音则进入待机（引擎仍听唤醒词）。
    # 与 max_duration_ms 同族（都是收听时序），故放在本段而非新增分段。
    # Silence timeout (ms) while waiting for a spoken answer; on timeout the assistant
    # enters standby (the engine still listens for the wake word). It lives here rather
    # than in a new section because it shares the family with max_duration_ms.
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
    # True=write/exec 高风险工具/任务不再询问操作者，自动放行（含子代理与技能；无人值守通道仍默认拒绝）
    auto_approve: bool = False  # True=auto-approve write/exec tools/tasks without asking the operator (incl. sub-agents & skills; channel-less runs still reject)
    # 操作者提问（澄清/确认）超时秒数：0=不限（无限期等待，旧行为）；>0 到期按拒绝处理
    # （fail-closed），前端问题卡随 timeout 源 answer 事件收起。
    # Timeout in seconds for operator questions (clarify/confirm): 0 = no limit (the old
    # wait-forever behaviour); on expiry the answer counts as a rejection (fail-closed)
    # and the frontend folds the question card via the timeout-sourced answer event.
    confirm_timeout_s: int = Field(0, ge=0)  # 0 = no limit (seconds); expiry counts as rejection (fail-closed)
    # 滚动压缩阈值（docs/designs/08 批2）：ReAct 历史估算字符超过此值时折叠中间段为摘要
    # （只动本轮 LLM 视角，不改会话持久化）；0=关闭。
    # Rolling-condense threshold (docs/designs/08 batch 2): fold the middle of the ReAct
    # history into a summary once the estimated characters exceed this (LLM view only,
    # never the persisted session); 0 = off.
    condense_threshold_chars: int = Field(12000, ge=0)


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
    """工具段配置：搜索/天气参数 + LLM 口径输出截断 + 渐进式 schema 分组。

    Tools section config: search/weather parameters + LLM-side output cap +
    progressive schema grouping.
    """

    model_config = ConfigDict(extra="forbid")

    search_max_results: int = Field(5, gt=0)
    weather_timeout: int = Field(10, gt=0)
    # LLM 口径输出截断（docs/designs/08 批2）：喂给模型的 tool 消息上限，超出截断并附
    # 「如何取更多」指引；0=不限。与展示口径（PREVIEW_LEN）/落库口径（HISTORY_LEN）独立。
    # LLM-side output cap (docs/designs/08 batch 2): limit for tool messages fed to the
    # model, truncated with a "how to get more" hint; 0 = unlimited. Independent of the
    # display (PREVIEW_LEN) and persistence (HISTORY_LEN) conventions.
    llm_max_output_chars: int = Field(8000, ge=0)
    # 渐进式工具 schema（docs/designs/08 批4）：这些组降级为一行简介（完整参数需先调
    # tools_describe）；默认空 = 全量下发（现状零变化）。例: ["mcp"]。
    # Progressive tool schemas (docs/designs/08 batch 4): groups in this list degrade to
    # one-line stubs (full parameters via tools_describe first); empty = full schemas
    # (today's behaviour unchanged). E.g. ["mcp"].
    lazy_groups: list[str] = Field(default_factory=list)


class PermissionRule(BaseModel):
    """一条权限规则：match 为工具名或 glob（fnmatch 语义，大小写敏感）。

    A permission rule: match is a tool name or a glob (fnmatch semantics, case-sensitive).
    """

    model_config = ConfigDict(extra="forbid")

    match: str
    action: Literal["allow", "ask", "deny"]


class PermissionTiers(BaseModel):
    """按工具风险层级设的默认动作。Per-tier default action, keyed by tool risk.

    ⚠️ 三档默认**全放行**（2026-09-13 按用户要求改）。本项目无沙箱，这道确认是任意命令
    执行前的唯一闸门 —— 全放行意味着**该闸门默认不生效**（`run_shell_tool` 可执行任意
    命令而不询问）。想收紧时改这里、或用 `permissions.rules` 里的 deny/ask 规则（规则按
    工具名 glob 匹配），也可在控制台「设置 → 权限」里改。

    ⚠️ All three tiers default to **allow** (changed 2026-09-13 at the user's request). There is
    no sandbox here and this confirmation is the only gate before arbitrary command execution, so
    allow-by-default means **the gate is off by default** (`run_shell_tool` runs any command
    without asking). To tighten it, edit these values, add deny/ask entries to
    `permissions.rules` (which glob against tool names), or use the console's Settings → Permissions.
    """

    model_config = ConfigDict(extra="forbid")

    read: Literal["allow", "ask", "deny"] = "allow"
    write: Literal["allow", "ask", "deny"] = "allow"
    exec: Literal["allow", "ask", "deny"] = "allow"


class PermissionsSection(BaseModel):
    """工具权限策略：层级默认 + 规则覆盖。

    默认值**三档全放行、兜底也放行**（2026-09-13 按用户要求从「read 免询问、write/exec
    询问」改为全放行）。想收紧就用 `rules`（按工具名 glob，deny 单调短路）或改 `tiers`。

    Tool permission policy: per-tier defaults plus rule overrides. Every tier — and the
    fallback — defaults to **allow** (changed 2026-09-13 at the user's request, from
    "read auto-allowed, write/exec asked"). To tighten it, use `rules` (globbed against tool
    names, with monotonic deny short-circuiting) or override `tiers`.
    """

    model_config = ConfigDict(extra="forbid")

    default_action: Literal["allow", "ask", "deny"] = "allow"
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
    """RAG 段配置：自动索引与精排档位（docs/designs/05）。

    RAG section config: auto-index and rerank tier (docs/designs/05).
    """

    model_config = ConfigDict(extra="forbid")

    auto_index: bool = True
    # 精排档位：none=纯 BM25（默认，零成本）；llm=BM25 粗排候选后单次 LLM 打分精排，
    # 任何失败静默回退 BM25 序（retriever.rerank 内 catch）。
    # Rerank tier: none = pure BM25 (default, zero cost); llm = one LLM scoring pass
    # over BM25 candidates, any failure silently falls back to BM25 order (caught
    # inside retriever.rerank).
    rerank: Literal["none", "llm"] = "none"
    rerank_candidates: int = Field(12, gt=0)   # 粗排候选数。BM25 candidate count.
    rerank_top_k: int = Field(5, gt=0)         # 精排后注入数（= none 档的 top-k）。Rows injected after rerank (= top-k in the none tier).


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
    # SSE 断线宽限（docs/designs/06）：断开后 runner 继续跑的秒数，期内可 /voice/resume
    # 续播；0=断线即收尾（旧行为）。仅配置文件可改（与 kws 段同为 config-file-only）。
    # SSE disconnect grace (docs/designs/06): seconds the runner keeps alive after a
    # disconnect, resumable via /voice/resume inside the window; 0 = wrap up on
    # disconnect (legacy behaviour). Config-file only (same as the kws section).
    resume_grace_s: int = Field(120, ge=0)


class MemorySection(BaseModel):
    """长期记忆段配置（docs/designs/04）：新近度加权、注入预算、提取回看深度。

    Long-term memory section config (docs/designs/04): recency weighting, injection
    budget, extraction lookback depth.
    """

    model_config = ConfigDict(extra="forbid")

    # 检索新近度加权：score' = bm25 × (1 + w × 0.5^(age_days/τ))；w=0 关闭（纯 bm25）。
    # Search recency weight: score' = bm25 × (1 + w × 0.5^(age_days/τ)); 0 disables.
    recency_half_life_days: float = Field(30.0, gt=0)
    recency_weight: float = Field(0.5, ge=0.0, le=5.0)
    # 注入预算：top-k 条数 + 字符上限（双闸，system prompt 不随命中数膨胀）。
    # Injection budget: top-k rows + character cap (two gates; the system prompt
    # cannot swell with hit count).
    inject_top_k: int = Field(5, gt=0)
    inject_max_chars: int = Field(800, gt=0)
    # 任务后提取回看的最近对话条数（用户/助手各 n；解「他/那里」类指代）。
    # Recent dialog lines the post-task extraction sees (n of each role; resolves
    # "he/there"-style references).
    extract_recent_messages: int = Field(2, ge=0)


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
    memory: MemorySection = Field(default_factory=lambda: MemorySection())
    agent: AgentSection = Field(default_factory=lambda: AgentSection())
    llm_client: LlmClientSection = Field(default_factory=lambda: LlmClientSection())
    tools: ToolsSection = Field(default_factory=lambda: ToolsSection())
    permissions: PermissionsSection = Field(default_factory=lambda: PermissionsSection())
    vendor_presets: dict[str, VendorPreset] = Field(default_factory=dict)  # 厂商目录 YAML 扩展
