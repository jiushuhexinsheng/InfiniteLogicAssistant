# -*- coding: utf-8 -*-
"""API 响应模型 — 全部 JSON 端点的 pydantic response_model（openapi schema 源）

前端 `npm run gen:api` 据此生成 TS 类型；改响应结构 → 重跑生成 → 前端类型同步。
不走 response_model 的端点：POST /api/tts（音频 bytes）、POST /api/voice/utter（SSE 事件流）。
"""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class ApiResponse(BaseModel):
    ok: bool = True
    error: str | None = None


# ─────────────────────────── ping / config / voice ───────────────────────────


class PingResponse(ApiResponse):
    time: str


class WakeWordConfig(BaseModel):
    enabled: bool = True
    keyword: str = ""
    sensitivity: float = 0.5
    model_path: str = ""


class VadConfig(BaseModel):
    silence_threshold: float = 0.02
    silence_duration_ms: int = 1500
    max_duration_ms: int = 10000


class ConfigResponse(ApiResponse):
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
    text: str = ""


class AckResponse(ApiResponse):
    ack: str = ""


# ─────────────────────────── tools ───────────────────────────


class FunctionParams(BaseModel):
    type: str = "object"
    properties: dict[str, Any] = {}
    required: list[str] = []


class ToolFunction(BaseModel):
    name: str
    description: str
    parameters: FunctionParams


class ToolSchema(BaseModel):
    type: str = "function"
    function: ToolFunction


class ToolsResponse(ApiResponse):
    tools: list[ToolSchema] = []


class ToolCallResponse(ApiResponse):
    status: str | None = None
    output: str | None = None
    needs_confirm: bool | None = None


# ─────────────────────────── env / memory ───────────────────────────


class EnvResponse(ApiResponse):
    content: str = ""


class FactItem(BaseModel):
    topic: str
    content: str
    source: str = ""
    ts: str = ""


class MemoryListResponse(ApiResponse):
    facts: list[FactItem] = []


# ─────────────────────────── schedules ───────────────────────────


class ScheduleItem(BaseModel):
    id: str
    cron: str
    prompt: str
    enabled: bool = True


class SchedulesResponse(ApiResponse):
    schedules: list[ScheduleItem] = []


class ScheduleAddResponse(ApiResponse):
    schedule: ScheduleItem | None = None


# ─────────────────────────── history ───────────────────────────


class HistoryMessage(BaseModel):
    role: str
    content: str = ""
    tool_calls: list[dict[str, Any]] | None = None


class HistoryConversation(BaseModel):
    id: str
    created: str
    updated: str
    status: str
    summary: str
    message_count: int


class HistoryListResponse(ApiResponse):
    conversations: list[HistoryConversation] = []


class HistoryConversationDetail(BaseModel):
    """会话详情：详情响应不含 message_count（仅列表接口统计）。"""

    id: str
    created: str
    updated: str
    status: str
    summary: str
    messages: list[HistoryMessage] = []


class HistoryDetailResponse(ApiResponse):
    conversation: HistoryConversationDetail | None = None


# ─────────────────────────── providers ───────────────────────────


class ProviderPreset(BaseModel):
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
    catalog: dict[str, list[ProviderPreset]] = {}


class FetchModelsResponse(ApiResponse):
    models: list[str] = []
    count: int = 0


# ─────────────────────────── settings ───────────────────────────


class ProfileEditable(BaseModel):
    """editable_snapshot 的 profile（去 api_key）。extra=allow 保留用户透传键。"""

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
    active: str = ""
    profiles: dict[str, ProfileEditable] = {}
    api_key_set: dict[str, bool] = {}


class TtsSectionEditable(SectionEditable):
    enabled: bool = False


class AgentConfigOut(BaseModel):
    recursion_limit: int = 12
    multi_agent: bool = False
    models_failover: list[str] = []


class LlmClientConfigOut(BaseModel):
    retry_max: int = 3
    retry_backoff_base: float = 0.5
    retry_backoff_max: float = 10.0
    circuit_breaker_threshold: int = 5
    circuit_breaker_cooldown: float = 30.0
    request_timeout: int = 60


class ToolsConfigOut(BaseModel):
    search_max_results: int = 5
    weather_timeout: int = 10


class McpServerOut(BaseModel):
    name: str
    command: str
    args: list[str] = []


class McpConfigOut(BaseModel):
    servers: list[McpServerOut] = []


class RagConfigOut(BaseModel):
    auto_index: bool = True


class ServerConfigOut(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8520
    open_browser: bool = True
    cors_origins: list[str] = []
    api_token_set: bool = False


class EditableSnapshot(BaseModel):
    llm: SectionEditable
    asr: SectionEditable
    tts: TtsSectionEditable
    wake_word: WakeWordConfig
    vad: VadConfig
    agent: AgentConfigOut
    llm_client: LlmClientConfigOut
    tools: ToolsConfigOut
    mcp: McpConfigOut
    rag: RagConfigOut
    server: ServerConfigOut


class ConfigFullResponse(ApiResponse):
    editable: EditableSnapshot


class PatchConfigResponse(ApiResponse):
    restart_required: bool = False


class PutSecretsResponse(ApiResponse):
    set: bool = False
    path: str = ""


# ─────────────────────────── detection ───────────────────────────


class DetectionIssue(BaseModel):
    level: str
    key: str
    message: str


class ConfigHealthOut(BaseModel):
    ok: bool
    issues: list[DetectionIssue] = []


class ConnectivityResult(BaseModel):
    name: str
    status: str
    latency_ms: int | None = None
    detail: str = ""


class DetectionReportOut(BaseModel):
    environment: dict[str, Any] = {}
    config: ConfigHealthOut
    connectivity: list[ConnectivityResult] = []


class DetectionResponse(ApiResponse):
    report: DetectionReportOut
