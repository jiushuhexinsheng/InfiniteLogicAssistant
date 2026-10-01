# -*- coding: utf-8 -*-
"""设置页编辑快照与配置端点响应。Settings-page editable snapshot and config endpoint responses."""
from typing import Any

from pydantic import BaseModel, ConfigDict

from .base import ApiResponse
from .voice import VadConfig, WakeWordConfig

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
    """Agent 配置输出（递归限制、多代理、故障转移模型列表、确认超时、压缩阈值）。

    Agent config output (recursion limit, multi-agent, failover model list, confirm
    timeout, condense threshold).
    """
    recursion_limit: int = 12
    multi_agent: bool = False
    models_failover: list[str] = []
    confirm_timeout_s: int = 0
    condense_threshold_chars: int = 12000

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
    llm_max_output_chars: int = 8000
    lazy_groups: list[str] = []

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
    rerank: str = "none"
    rerank_candidates: int = 12
    rerank_top_k: int = 5

class MemoryConfigOut(BaseModel):
    """记忆配置输出（新近度加权 / 注入预算 / 提取回看，docs/designs/04）。

    Memory config output (recency weight / injection budget / extraction lookback,
    docs/designs/04).
    """
    recency_half_life_days: float = 30.0
    recency_weight: float = 0.5
    inject_top_k: int = 5
    inject_max_chars: int = 800
    extract_recent_messages: int = 2

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
    memory: MemoryConfigOut
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

