# -*- coding: utf-8 -*-
"""环境与记忆端点响应。Environment and memory endpoint responses."""
from typing import Any

from pydantic import BaseModel

from .base import ApiResponse

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

