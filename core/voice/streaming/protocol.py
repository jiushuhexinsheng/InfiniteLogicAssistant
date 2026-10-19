# -*- coding: utf-8 -*-
"""WebSocket 消息发送小工具（协议字段在各事件构造处写清楚）。

Small WebSocket send helper (message fields are documented where each event is built).
"""
from __future__ import annotations

from typing import Any


async def send(ws: Any, payload: dict[str, Any]) -> None:
    """发送一条 JSON 事件；连接已断时静默返回。

    Send one JSON event; stay silent when the connection is already gone.
    """
    try:
        await ws.send_json(payload)
    except Exception:
        # 对端断开是正常生命周期，不把异常抛回会话主循环。
        # A peer disconnect is a normal lifecycle event; do not surface it to the loop.
        return
