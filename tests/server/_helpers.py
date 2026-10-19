# -*- coding: utf-8 -*-
"""tests/server 共享桩件与端点表。Shared stubs and endpoint tables for the server test package."""


class _NoAsr:
    """ASR 不可用桩，隔离真实网络。
    A stub for an unavailable ASR, isolating real network access.
    """

    def available(self):
        return False


class _FakeLLMClient:
    """模拟 LlmClient.retry_stream_chat，隔离真实网络。
    A fake LlmClient.retry_stream_chat, isolating real network access.
    """

    def __init__(self, events):
        self.events = events

    async def retry_stream_chat(self, messages, tools=None, *, profile=None, **kwargs):
        for e in self.events:
            yield e


# 旧切段上传链路已删除；音频只走 WebSocket /api/voice/asr/stream（不在 OpenAPI 的 POST 表里）。
# The legacy segment-upload pipeline is gone; audio travels only over the WebSocket
# /api/voice/asr/stream (not part of the OpenAPI POST table).
