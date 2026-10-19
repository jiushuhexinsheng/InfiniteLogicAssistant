# -*- coding: utf-8 -*-
"""流式语音 WebSocket 端点。

Streaming voice WebSocket endpoint.

``/api/voice/asr/stream``：客户端先发 ``start``（JSON），随后发送 PCM16 二进制帧；
服务端返回 ready / vad / partial / final / wake / error / done。

One connection first sends ``start`` (JSON), then PCM16 binary frames; the server sends
ready / vad / partial / final / wake / error / done.

⚠️ HTTP 认证中间件不覆盖 WebSocket：配置了 ``server.api_token`` 时，token 必须通过
``?token=`` 或 ``X-API-Token`` 头携带。
The HTTP auth middleware does not cover WebSockets: when ``server.api_token`` is set,
the token must travel via ``?token=`` or the ``X-API-Token`` header.
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core import config
from core.logger import logger
from core.voice.streaming import SessionError, StreamingSession

router = APIRouter()


def _authorized(ws: WebSocket) -> bool:
    """WebSocket 鉴权：未配置 token 时放行；配置后校验查询参数或头。

    WebSocket auth: allow when no token is configured; otherwise check the query
    parameter or header.
    """
    token = config.settings.server.api_token
    if not token:
        return True
    supplied = ws.query_params.get("token") or ws.headers.get("x-api-token") or ""
    return supplied == token


@router.websocket("/voice/asr/stream")
async def voice_asr_stream(ws: WebSocket):
    """流式会话入口。Streaming-session entry point."""
    await ws.accept()
    if not _authorized(ws):
        await ws.close(code=4401)
        return

    try:
        first = await asyncio.wait_for(ws.receive(), timeout=10.0)
    except asyncio.TimeoutError:
        await ws.close(code=4408)
        return

    if first.get("type") == "websocket.disconnect":
        return
    raw = first.get("text")
    if raw is None:
        await ws.send_json({"type": "error", "code": "start_required",
                            "message": "首条消息必须是 start JSON"})
        await ws.close(code=4400)
        return
    try:
        start = json.loads(raw)
    except Exception:
        start = {}
    if not isinstance(start, dict) or start.get("type") != "start":
        await ws.send_json({"type": "error", "code": "start_required",
                            "message": "首条消息必须是 start JSON"})
        await ws.close(code=4400)
        return

    session = StreamingSession(ws, start)
    try:
        await session.start_session()
    except SessionError as e:
        await ws.send_json({"type": "error", "code": e.code, "message": e.message,
                            "recoverable": False})
        await ws.close(code=1011)
        return
    except Exception as e:  # noqa: BLE001
        logger.error("流式语音会话启动失败: {}", e)
        await ws.send_json({"type": "error", "code": "start_failed",
                            "message": str(e), "recoverable": False})
        await ws.close(code=1011)
        return

    try:
        await session.run()
    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001
        logger.error("流式语音会话异常: {}", e)
        try:
            await ws.send_json({"type": "error", "code": "session_failed",
                                "message": str(e), "recoverable": False})
        except Exception:
            pass
