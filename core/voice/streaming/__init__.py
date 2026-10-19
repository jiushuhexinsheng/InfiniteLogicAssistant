# -*- coding: utf-8 -*-
"""流式语音会话（WebSocket）。

Streaming voice session (WebSocket).

一个连接 = 一路麦克风：客户端送 20 ms PCM16 帧，服务端做本地 VAD → KWS → ASR，
返回 partial / final / wake。这里不保留旧的「浏览器切段再上传」链路。

One connection = one microphone: the client sends 20 ms PCM16 frames, the server runs
local VAD → KWS → ASR and returns partial / final / wake. The legacy "browser segments
then uploads" pipeline is not kept.
"""
from __future__ import annotations

from .session import StreamingSession, SessionError

__all__ = ["StreamingSession", "SessionError"]
