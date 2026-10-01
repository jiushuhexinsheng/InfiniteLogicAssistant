# -*- coding: utf-8 -*-
"""工具端点响应。Tool endpoint responses."""
from typing import Any

from pydantic import BaseModel

from .base import ApiResponse

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

