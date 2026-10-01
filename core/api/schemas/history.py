# -*- coding: utf-8 -*-
"""历史会话端点响应。Conversation-history endpoint responses."""
from typing import Any

from pydantic import BaseModel

from .base import ApiResponse

# ─────────────────────────── history ───────────────────────────

class HistoryMessage(BaseModel):
    """历史记录中的单条消息。

    content 是纯文本投影（LLM 回喂降级与摘要取用）；blocks 为消息块协议的
    块列表（消息恒带 blocks，旧历史已清除）。tool_calls 已废弃（块协议的
    tool 块取代），保留字段仅供 API 形状稳定。

    A single message in a conversation history. content is the plain-text
    projection (for LLM feed fallback and summaries); blocks is the
    message-block-protocol list (messages always carry blocks; old history has
    been dropped). tool_calls is deprecated (superseded by tool blocks) and kept
    only for API shape stability.
    """
    role: str
    content: str = ""
    tool_calls: list[dict[str, Any]] | None = None  # 废弃保留（deprecated）
    blocks: list[dict[str, Any]] = []
    turn_id: str | None = None
    ts: str | None = None

class HistoryConversation(BaseModel):
    """历史会话摘要（列表视图）。

    Conversation summary (list view).
    """
    id: str
    created: str
    updated: str
    status: str
    summary: str
    message_count: int

class HistoryListResponse(ApiResponse):
    """历史会话列表端点响应。

    ``/api/history`` conversation list response.
    """
    conversations: list[HistoryConversation] = []

class HistoryConversationDetail(BaseModel):
    """会话详情：详情响应不含 message_count（仅列表接口统计）。

    Conversation detail: excludes ``message_count`` (only counted in the list
    endpoint).
    """

    id: str
    created: str
    updated: str
    status: str
    summary: str
    messages: list[HistoryMessage] = []

class HistoryDetailResponse(ApiResponse):
    """历史会话详情端点响应。

    ``/api/history/<id>`` detail response.
    """
    conversation: HistoryConversationDetail | None = None

