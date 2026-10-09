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


# 会携带音频、因而必须逐条记上传审计的 `/api/voice/*` 端点 → 其审计行的 `via=` 取值。
# 这张表是**判据的一部分**（见 test_server_wake_audit 中的成本口径用例），不是随手抄的清单。
#
# The `/api/voice/*` endpoints that carry audio and must therefore audit every upload, mapped to
# their `via=` value. This table is **part of the criterion** (see the cost-accounting test in
# test_server_wake_audit), not a casual list.
_AUDIO_UPLOAD_ENDPOINTS = {
    "/api/voice/wake": "wake",
    "/api/voice/transcribe": "transcribe",
    "/api/voice/call/segment": "call-segment",
}

# 明确**不**携带音频、因而不记上传审计的 `/api/voice/*` 端点。逐条附理由，免得日后被当成漏网。
# `/api/voice/*` endpoints that explicitly do NOT carry audio, so they are not audited as uploads.
# Each carries its reason so a later reader cannot mistake it for an oversight.
_NON_UPLOAD_VOICE_ENDPOINTS = {
    "/api/voice/utter": "只收文本走 SSE 事件流，不出音频。Text in, SSE event stream out; no audio.",
    "/api/voice/answer": "只把文本/choice 投给编排层（channel.answer），无 ASR、无 HTTP。"
                         "Text/choice handed to the orchestrator's channel.answer; no ASR, no HTTP.",
    "/api/voice/wake/check": "本地 KWS 快检：音频只到本机判定（sherpa-onnx），不调云端 ASR。"
                             "Local KWS quick check: audio is judged on-box (sherpa-onnx), no cloud ASR.",
    "/api/voice/resume": "断线重连只回放缓冲区里的 SSE 事件，请求体只有 session_id/last_seq，"
                         "无音频、无 ASR。Reconnect replays buffered SSE events only; the body is "
                         "session_id/last_seq — no audio, no ASR.",
    "/api/voice/call/start": "只建/刷新通话会话态（内存 dataclass），请求体为空、无音频、无 ASR。"
                             "Only creates/refreshes the in-memory call session; empty body, no audio, no ASR.",
    "/api/voice/call/stop": "只清通话会话态，请求体为空、无音频、无 ASR。"
                            "Only clears the call session; empty body, no audio, no ASR.",
}
