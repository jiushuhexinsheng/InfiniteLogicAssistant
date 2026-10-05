# -*- coding: utf-8 -*-
"""API 响应模型 — 全部 JSON 端点的 pydantic response_model（openapi schema 源）

前端 `npm run gen:api` 据此生成 TS 类型；改响应结构 → 重跑生成 → 前端类型同步。
不走 response_model 的端点：POST /api/tts（音频 bytes）、POST /api/voice/utter（SSE 事件流）。

按领域拆分到同目录子模块（base / voice / tools / memory / schedules / history /
sessions / providers / settings / detection / library）；此处全量 re-export,
`from core.api.schemas import X` 的调用方零改动。

API response models — Pydantic ``response_model`` for every JSON endpoint
(also the OpenAPI schema source).

Front-end ``npm run gen:api`` derives TS types from these models; after changing
response structures, re-run the generator to keep TS types in sync.
Endpoints excluded from ``response_model``: ``POST /api/tts`` (audio bytes),
``POST /api/voice/utter`` (SSE event stream).

Split per domain into sibling submodules (base / voice / tools / memory /
schedules / history / sessions / providers / settings / detection / library);
everything is re-exported here so ``from core.api.schemas import X`` callers
keep working unchanged.
"""
from .base import (
    AckResponse,
    ApiResponse,
    PingResponse,
    TextResponse,
)
from .detection import (
    ConfigHealthOut,
    ConnectivityResult,
    DetectionIssue,
    DetectionReportOut,
    DetectionResponse,
)
from .history import (
    HistoryConversation,
    HistoryConversationDetail,
    HistoryDetailResponse,
    HistoryListResponse,
    HistoryMessage,
)
from .library import (
    LibraryDetailResponse,
    LibraryListResponse,
    TaskLibraryItem,
)
from .memory import (
    EnvResponse,
    FactItem,
    MemoryListResponse,
)
from .providers import (
    CatalogResponse,
    FetchModelsResponse,
    ProviderPreset,
)
from .schedules import (
    ScheduleAddResponse,
    ScheduleItem,
    SchedulesResponse,
)
from .sessions import (
    SessionCreateResponse,
    SessionListResponse,
    SessionOut,
)
from .settings import (
    AgentConfigOut,
    ConfigFullResponse,
    EditableSnapshot,
    LlmClientConfigOut,
    McpConfigOut,
    McpServerOut,
    MemoryConfigOut,
    PatchConfigResponse,
    PermissionRuleOut,
    PermissionsOut,
    PermissionTiersOut,
    ProfileEditable,
    PutSecretsResponse,
    RagConfigOut,
    SectionEditable,
    ServerConfigOut,
    ToolsConfigOut,
    TtsSectionEditable,
)
from .tools import (
    FunctionParams,
    ToolCallResponse,
    ToolFunction,
    ToolSchema,
    ToolsResponse,
)
from .voice import (
    CallConfig,
    CallSegmentResponse,
    CallSessionResponse,
    ConfigResponse,
    VadConfig,
    WakeCheckResponse,
    WakeResponse,
    WakeWordConfig,
)

__all__ = [
    "AckResponse",
    "AgentConfigOut",
    "ApiResponse",
    "CallConfig",
    "CallSegmentResponse",
    "CallSessionResponse",
    "CatalogResponse",
    "ConfigFullResponse",
    "ConfigHealthOut",
    "ConfigResponse",
    "ConnectivityResult",
    "DetectionIssue",
    "DetectionReportOut",
    "DetectionResponse",
    "EditableSnapshot",
    "EnvResponse",
    "FactItem",
    "FetchModelsResponse",
    "FunctionParams",
    "HistoryConversation",
    "HistoryConversationDetail",
    "HistoryDetailResponse",
    "HistoryListResponse",
    "HistoryMessage",
    "LibraryDetailResponse",
    "LibraryListResponse",
    "LlmClientConfigOut",
    "McpConfigOut",
    "McpServerOut",
    "MemoryConfigOut",
    "MemoryListResponse",
    "PatchConfigResponse",
    "PermissionRuleOut",
    "PermissionsOut",
    "PermissionTiersOut",
    "PingResponse",
    "ProfileEditable",
    "ProviderPreset",
    "PutSecretsResponse",
    "RagConfigOut",
    "ScheduleAddResponse",
    "ScheduleItem",
    "SchedulesResponse",
    "SectionEditable",
    "ServerConfigOut",
    "SessionCreateResponse",
    "SessionListResponse",
    "SessionOut",
    "TaskLibraryItem",
    "TextResponse",
    "ToolCallResponse",
    "ToolFunction",
    "ToolSchema",
    "ToolsConfigOut",
    "ToolsResponse",
    "TtsSectionEditable",
    "VadConfig",
    "WakeCheckResponse",
    "WakeResponse",
    "WakeWordConfig",
]
