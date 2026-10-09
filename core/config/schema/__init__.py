# -*- coding: utf-8 -*-
"""配置 schema — pydantic 强类型模型（纯定义，无 IO / 无全局状态）

Configuration schema — pydantic strongly-typed models (pure definitions, no IO / no global state).

加载时经 pydantic 模型校验（类型 / 范围 / 枚举，写错配置启动即报错）。
结构对应 config.yaml：llm / voice / server / mcp / rag / agent / llm_client / tools + vendor_presets。

自单文件 schema.py 拆包（纯移动）：本门面全量 re-export 全部类，
`from core.config.schema import X` 与 `from core.config import schema` 两种导入面不变。
"""
from .profiles import (
    AsrProfile,
    AsrSection,
    CompatConfig,
    LlmProfile,
    LlmSection,
    ProfileBase,
    TtsProfile,
    TtsSection,
    VendorPreset,
)
from .sections import (
    AgentSection,
    LlmClientSection,
    McpSection,
    McpServer,
    MemorySection,
    PermissionRule,
    PermissionTiers,
    PermissionsSection,
    RagSection,
    ServerSection,
    ToolsSection,
)
from .settings import Settings
from .voice import CallConfig, KwsConfig, VadConfig, VoiceSection, WakeWordConfig

__all__ = [
    "AgentSection",
    "AsrProfile",
    "AsrSection",
    "CallConfig",
    "CompatConfig",
    "KwsConfig",
    "LlmClientSection",
    "LlmProfile",
    "LlmSection",
    "McpSection",
    "McpServer",
    "MemorySection",
    "PermissionRule",
    "PermissionTiers",
    "PermissionsSection",
    "ProfileBase",
    "RagSection",
    "ServerSection",
    "Settings",
    "TtsProfile",
    "TtsSection",
    "ToolsSection",
    "VendorPreset",
    "VadConfig",
    "VoiceSection",
    "WakeWordConfig",
]
