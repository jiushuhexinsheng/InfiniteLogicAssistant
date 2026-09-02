# -*- coding: utf-8 -*-
"""core.config — 全局配置包（兼容层，对外 API 与旧 core/config.py 单文件完全一致）

core.config — the global configuration package (compatibility layer whose public API is fully
consistent with the legacy single-file core/config.py).

拆分：
- constants.py   路径与常量
- schema.py      pydantic 模型定义
- loader.py      YAML 读取 + 密钥注入 + 构建（纯函数）
- runtime.py     全局单例 + 热重载 + profile 解析 + 设置快照

Split:
- constants.py   paths and constants
- schema.py      pydantic model definitions
- loader.py      YAML reading + secret injection + building (pure functions)
- runtime.py     global singleton + hot reload + profile resolution + settings snapshot

保持两种引用方式可用，且无需改动调用方：
    from core import config            # config.settings 仍指向当前单例（reload 后自动拿新值）
    from core.config import ROOT_DIR / Settings / resolve_llm_profile / ensure_dirs / ...

Both import styles keep working with no caller changes:
    from core import config            # config.settings still points to the current singleton (fresh values after reload)
    from core.config import ROOT_DIR / Settings / resolve_llm_profile / ensure_dirs / ...
"""
from core.config.constants import (
    CONFIG_FILE, EXAMPLE_FILE, ROOT_DIR, SECRETS_EXAMPLE, SECRETS_FILE, _ENV_KEY_MAP,
)
from core.config.loader import (
    _build, _inject_secrets, _load_secrets, _profile_api_key, _read_yaml, _resolve_env,
    profile_api_key,
)
from core.config.runtime import (
    _reload_hooks, _settings, add_reload_hook, editable_snapshot, ensure_dirs,
    get_settings, is_asr_configured, is_llm_configured, is_tts_enabled,
    reload_settings, resolve_asr_profile, resolve_llm_profile, resolve_tts_profile,
)
from core.config.schema import (
    AgentSection, AsrProfile, AsrSection, CompatConfig, LlmClientSection, LlmProfile,
    LlmSection, McpSection, McpServer, ProfileBase, RagSection, ServerSection, Settings,
    ToolsSection, TtsProfile, TtsSection, VadConfig, VendorPreset, VoiceSection,
    WakeWordConfig,
)

__all__ = [
    # constants
    "ROOT_DIR", "CONFIG_FILE", "EXAMPLE_FILE", "SECRETS_FILE", "SECRETS_EXAMPLE", "_ENV_KEY_MAP",
    # schema
    "Settings", "VendorPreset", "CompatConfig", "ProfileBase",
    "LlmProfile", "AsrProfile", "TtsProfile",
    "LlmSection", "AsrSection", "TtsSection",
    "WakeWordConfig", "VadConfig", "VoiceSection",
    "AgentSection", "LlmClientSection", "ToolsSection",
    "McpServer", "McpSection", "RagSection", "ServerSection",
    # loader
    "_read_yaml", "_resolve_env", "_load_secrets", "_profile_api_key", "_inject_secrets",
    "profile_api_key", "_build",
    # runtime
    "_settings", "_reload_hooks",
    "add_reload_hook", "get_settings", "reload_settings",
    "resolve_llm_profile", "resolve_asr_profile", "resolve_tts_profile",
    "is_llm_configured", "is_asr_configured", "is_tts_enabled",
    "editable_snapshot", "ensure_dirs",
]


def __getattr__(name: str):
    """模块级属性动态解析：仅支持 settings，返回当前配置单例。

    Dynamically resolve module-level attributes: only "settings" is supported, returning
    the current configuration singleton.
    """
    # config.settings 始终指向当前单例（reload 后自动拿到新值）
    if name == "settings":
        return get_settings()
    raise AttributeError(name)
