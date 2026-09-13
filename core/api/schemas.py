# -*- coding: utf-8 -*-
"""API 响应模型 — 全部 JSON 端点的 pydantic response_model（openapi schema 源）

前端 `npm run gen:api` 据此生成 TS 类型；改响应结构 → 重跑生成 → 前端类型同步。
不走 response_model 的端点：POST /api/tts（音频 bytes）、POST /api/voice/utter（SSE 事件流）。

API response models — Pydantic ``response_model`` for every JSON endpoint
(also the OpenAPI schema source).

Front-end ``npm run gen:api`` derives TS types from these models; after changing
response structures, re-run the generator to keep TS types in sync.
Endpoints excluded from ``response_model``: ``POST /api/tts`` (audio bytes),
``POST /api/voice/utter`` (SSE event stream).
"""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class ApiResponse(BaseModel):
    """所有 API 响应的基类，含通用 ok/error 字段。

    Base class for all API responses, with common ``ok`` / ``error`` fields.
    """
    ok: bool = True
    error: str | None = None


# ─────────────────────────── ping / config / voice ───────────────────────────


class PingResponse(ApiResponse):
    """ping 端点响应，返回服务器时间戳。

    ``/api/ping`` response carrying the server timestamp.
    """
    time: str


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
    keywords: list[str] = []
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


class TextResponse(ApiResponse):
    """返回纯文本内容的通用响应。

    Generic response returning plain text content.
    """
    text: str = ""


class AckResponse(ApiResponse):
    """操作确认响应。

    Operation acknowledgement response.
    """
    ack: str = ""


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


# ─────────────────────────── tools ───────────────────────────


class FunctionParams(BaseModel):
    """工具函数参数的 JSON Schema 描述。

    JSON Schema description of tool function parameters.
    """
    type: str = "object"
    properties: dict[str, Any] = {}
    required: list[str] = []


class ToolFunction(BaseModel):
    """单个工具函数的元数据（名称 + 描述 + 参数 schema）。

    Metadata for a single tool function (name + description + parameter schema).
    """
    name: str
    description: str
    parameters: FunctionParams


class ToolSchema(BaseModel):
    """工具定义（含 function 字段，符合 OpenAI tools schema）。

    Tool definition (with ``function`` field, compatible with OpenAI tools schema).
    """
    type: str = "function"
    function: ToolFunction


class ToolsResponse(ApiResponse):
    """工具列表端点响应。

    ``/api/tools`` list response.
    """
    tools: list[ToolSchema] = []


class ToolCallResponse(ApiResponse):
    """工具调用端点响应。

    ``/api/tools/call`` response.
    """
    status: str | None = None
    output: str | None = None
    needs_confirm: bool | None = None


# ─────────────────────────── env / memory ───────────────────────────


class EnvResponse(ApiResponse):
    """环境信息端点响应（environment.md 内容）。

    ``/api/env`` response (content of ``environment.md``).
    """
    content: str = ""


class FactItem(BaseModel):
    """单条长期记忆事实。

    A single long-term memory fact entry.
    """
    topic: str
    content: str
    source: str = ""
    ts: str = ""


class MemoryListResponse(ApiResponse):
    """记忆列表端点响应。

    ``/api/memory`` list response.
    """
    facts: list[FactItem] = []


# ─────────────────────────── schedules ───────────────────────────


class ScheduleItem(BaseModel):
    """单条定时任务。

    A single scheduled task entry.
    """
    id: str
    cron: str
    prompt: str
    enabled: bool = True


class SchedulesResponse(ApiResponse):
    """定时任务列表端点响应。

    ``/api/schedules`` list response.
    """
    schedules: list[ScheduleItem] = []


class ScheduleAddResponse(ApiResponse):
    """添加定时任务端点响应。

    ``/api/schedules/add`` response.
    """
    schedule: ScheduleItem | None = None


# ─────────────────────────── history ───────────────────────────


class HistoryMessage(BaseModel):
    """历史记录中的单条消息。

    A single message in a conversation history.
    """
    role: str
    content: str = ""
    tool_calls: list[dict[str, Any]] | None = None


class HistoryConversation(BaseModel):
    """历史会话摘要（列表视图）。

    Conversation summary (list view).
    """
    id: str
    created: str
    updated: str
    status: str
    summary: str
    message_count: int


class HistoryListResponse(ApiResponse):
    """历史会话列表端点响应。

    ``/api/history`` conversation list response.
    """
    conversations: list[HistoryConversation] = []


class HistoryConversationDetail(BaseModel):
    """会话详情：详情响应不含 message_count（仅列表接口统计）。

    Conversation detail: excludes ``message_count`` (only counted in the list
    endpoint).
    """

    id: str
    created: str
    updated: str
    status: str
    summary: str
    messages: list[HistoryMessage] = []


class HistoryDetailResponse(ApiResponse):
    """历史会话详情端点响应。

    ``/api/history/<id>`` detail response.
    """
    conversation: HistoryConversationDetail | None = None


# ─────────────────────────── sessions（会话管理）───────────────────────────


class SessionOut(BaseModel):
    """会话输出模型。

    Session output model.
    """
    id: str
    name: str = ""
    created: str = ""
    updated: str = ""
    status: str = ""
    summary: str = ""
    message_count: int = 0
    archived: bool = False


class SessionListResponse(ApiResponse):
    """会话列表端点响应。

    ``/api/sessions`` list response.
    """
    sessions: list[SessionOut] = []


class SessionCreateResponse(ApiResponse):
    """创建会话端点响应。

    ``/api/sessions`` creation response.
    """
    session: SessionOut


# ─────────────────────────── providers ───────────────────────────


class ProviderPreset(BaseModel):
    """厂商预设的完整结构（含所有可用字段）。

    Full vendor preset structure (with all available fields).
    """
    id: str
    kind: Literal["llm", "asr", "tts"]
    label: str = ""
    provider: str = "openai"
    endpoint: str = ""
    chat_path: str = ""
    models_path: str | None = None
    models: list[str] = []
    vision_models: list[str] = []
    voices: list[str] = []
    api_key_env: str = ""
    compat: dict[str, Any] = {}
    defaults: dict[str, Any] = {}


class CatalogResponse(ApiResponse):
    """厂商目录端点响应。

    ``/api/providers/catalog`` response.
    """
    catalog: dict[str, list[ProviderPreset]] = {}


class FetchModelsResponse(ApiResponse):
    """获取模型列表端点响应。

    ``/api/providers/models`` fetch response.
    """
    models: list[str] = []
    count: int = 0


# ─────────────────────────── settings ───────────────────────────


class ProfileEditable(BaseModel):
    """editable_snapshot 的 profile（去 api_key）。extra=allow 保留用户透传键。

    Profile within ``editable_snapshot`` (``api_key`` stripped). ``extra=allow``
    preserves user pass-through keys.
    """

    model_config = ConfigDict(extra="allow")

    provider: str = "openai"
    vendor: str = ""
    endpoint: str = ""
    model: str = ""
    vision_model: str = ""
    chat_path: str = ""
    api_key_env: str = ""
    timeout: int = 30
    max_tokens: int = 4096
    temperature: float = 0.7
    language: str = "zh"
    voice: str = ""
    format: str = "wav"
    voice_ref: str | None = None
    models: list[str] = []
    models_path: str = ""
    voices: list[str] = []
    compat: dict[str, Any] = {}


class SectionEditable(BaseModel):
    """配置编辑区段（active profile + profiles 映射 + api_key_set 标记）。

    Editable configuration section (active profile + profiles mapping +
    ``api_key_set`` flags).
    """
    active: str = ""
    profiles: dict[str, ProfileEditable] = {}
    api_key_set: dict[str, bool] = {}


class TtsSectionEditable(SectionEditable):
    """TTS 区段（多一个 enabled 标记）。

    TTS section (extra ``enabled`` flag).
    """
    enabled: bool = False


class AgentConfigOut(BaseModel):
    """Agent 配置输出（递归限制、多代理、故障转移模型列表）。

    Agent config output (recursion limit, multi-agent, failover model list).
    """
    recursion_limit: int = 12
    multi_agent: bool = False
    models_failover: list[str] = []


class LlmClientConfigOut(BaseModel):
    """LLM 客户端配置输出（重试、熔断、超时参数）。

    LLM client config output (retry, circuit breaker, timeout parameters).
    """
    retry_max: int = 3
    retry_backoff_base: float = 0.5
    retry_backoff_max: float = 10.0
    circuit_breaker_threshold: int = 5
    circuit_breaker_cooldown: float = 30.0
    request_timeout: int = 60


class ToolsConfigOut(BaseModel):
    """工具配置输出。

    Tools config output.
    """
    search_max_results: int = 5
    weather_timeout: int = 10


class McpServerOut(BaseModel):
    """单个 MCP 服务器配置。

    A single MCP server configuration.
    """
    name: str
    command: str
    args: list[str] = []


class McpConfigOut(BaseModel):
    """MCP 配置输出。

    MCP config output.
    """
    servers: list[McpServerOut] = []


class RagConfigOut(BaseModel):
    """RAG 配置输出。

    RAG config output.
    """
    auto_index: bool = True


class ServerConfigOut(BaseModel):
    """服务器配置输出（主机、端口、浏览器启动、CORS、API token）。

    Server config output (host, port, browser launch, CORS, API token).
    """
    host: str = "127.0.0.1"
    port: int = 8520
    open_browser: bool = True
    cors_origins: list[str] = []
    api_token_set: bool = False


class PermissionRuleOut(BaseModel):
    """权限规则（前端展示与编辑用）。A permission rule (for front-end display and editing)."""
    match: str
    action: str


class PermissionTiersOut(BaseModel):
    """各风险层级的默认动作。The default action per risk tier."""
    read: str
    write: str
    exec: str


class PermissionsOut(BaseModel):
    """工具权限策略快照。Tool permission policy snapshot."""
    default_action: str
    tiers: PermissionTiersOut
    rules: list[PermissionRuleOut]


class EditableSnapshot(BaseModel):
    """配置编辑快照（前端 settings 页面的数据源）。

    Configuration editable snapshot (data source for the front-end settings page).
    """
    llm: SectionEditable
    asr: SectionEditable
    tts: TtsSectionEditable
    wake_word: WakeWordConfig
    vad: VadConfig
    agent: AgentConfigOut
    llm_client: LlmClientConfigOut
    tools: ToolsConfigOut
    permissions: PermissionsOut
    mcp: McpConfigOut
    rag: RagConfigOut
    server: ServerConfigOut


class ConfigFullResponse(ApiResponse):
    """完整配置端点响应。

    ``/api/config`` full response.
    """
    editable: EditableSnapshot


class PatchConfigResponse(ApiResponse):
    """配置补丁端点响应。

    ``PATCH /api/config`` response.
    """
    restart_required: bool = False


class PutSecretsResponse(ApiResponse):
    """密钥写入端点响应。

    ``PUT /api/secrets`` response.
    """
    set: bool = False
    path: str = ""


# ─────────────────────────── detection ───────────────────────────


class DetectionIssue(BaseModel):
    """单条检测问题（级别 + 键 + 描述）。

    A single detection issue (level + key + message).
    """
    level: str
    key: str
    message: str


class ConfigHealthOut(BaseModel):
    """配置健康状态输出。

    Configuration health status output.
    """
    ok: bool
    issues: list[DetectionIssue] = []


class ConnectivityResult(BaseModel):
    """单条连通性检查结果。

    A single connectivity check result.
    """
    name: str
    status: str
    latency_ms: int | None = None
    detail: str = ""


class DetectionReportOut(BaseModel):
    """环境检测报告（系统信息 + 配置健康 + 连通性检查）。

    Environment detection report (system info + config health + connectivity checks).
    """
    environment: dict[str, Any] = {}
    config: ConfigHealthOut
    connectivity: list[ConnectivityResult] = []


class DetectionResponse(ApiResponse):
    """环境检测端点响应。

    ``/api/detection`` response.
    """
    report: DetectionReportOut


class TaskLibraryItem(BaseModel):
    """任务库条目（一次成功任务的存档）。

    One archived successful task.
    """
    id: int
    goal: str
    params: dict[str, Any] = {}
    steps: list[Any] = []
    status: str = ""
    created: str = ""
    session_id: str = ""


class LibraryListResponse(ApiResponse):
    """任务库列表响应。

    The task-library list response.
    """
    tasks: list[TaskLibraryItem] = []


class LibraryDetailResponse(ApiResponse):
    """任务库详情响应。

    The task-library detail response.
    """
    task: TaskLibraryItem
