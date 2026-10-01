# -*- coding: utf-8 -*-
"""厂商目录端点响应。Vendor catalog endpoint responses."""
from typing import Any, Literal

from pydantic import BaseModel

from .base import ApiResponse

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

