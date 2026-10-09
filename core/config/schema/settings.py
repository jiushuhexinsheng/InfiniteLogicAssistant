# -*- coding: utf-8 -*-
"配置 schema — 顶层 Settings（自 schema.py 拆出，纯移动）。"

from pydantic import BaseModel, ConfigDict, Field

from .profiles import LlmSection, VendorPreset
from .sections import (
    AgentSection, LlmClientSection, McpSection, MemorySection, PermissionsSection,
    RagSection, ServerSection, ToolsSection,
)
from .voice import VoiceSection

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
