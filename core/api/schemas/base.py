# -*- coding: utf-8 -*-
"""通用基类与杂项响应。Generic base and misc response models."""
from pydantic import BaseModel

class ApiResponse(BaseModel):
    """所有 API 响应的基类，含通用 ok/error 字段。

    Base class for all API responses, with common ``ok`` / ``error`` fields.
    """
    ok: bool = True
    error: str | None = None

# ─────────────────────────── ping / config / voice ───────────────────────────

class PingResponse(ApiResponse):
    """ping 端点响应，返回服务器时间戳。

    ``/api/ping`` response carrying the server timestamp.
    """
    time: str

class TextResponse(ApiResponse):
    """返回纯文本内容的通用响应。

    Generic response returning plain text content.
    """
    text: str = ""

class AckResponse(ApiResponse):
    """操作确认响应。

    Operation acknowledgement response.
    """
    ack: str = ""
