# -*- coding: utf-8 -*-
"""会话管理端点响应。Session-management endpoint responses."""
from pydantic import BaseModel

from .base import ApiResponse

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

