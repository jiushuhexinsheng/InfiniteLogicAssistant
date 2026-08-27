# -*- coding: utf-8 -*-
"""core/voice — ASR 客户端 compat 兼容开关（小米 MiMo ASR：api-key 头 / data URL 前缀 / asr_options）"""
import pytest

import core.voice as voice_mod


class _FakeResp:
    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": "你好"}}]}


class _FakeClient:
    def __init__(self, *a, **kw):
        self.captured = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, headers=None):
        self.captured = {"url": url, "json": json, "headers": headers}
        return _FakeResp()


def _client_with_profile(monkeypatch, prof: dict):
    fake = _FakeClient()
    monkeypatch.setattr(voice_mod, "resolve_asr_profile", lambda: ("xiaomi", prof))
    monkeypatch.setattr(voice_mod.httpx, "AsyncClient", lambda *a, **kw: fake)
    return voice_mod.ASRClient(), fake


@pytest.mark.asyncio
async def test_asr_mimo_compat_headers_data_url_language(monkeypatch):
    prof = {
        "provider": "openai", "endpoint": "https://api.xiaomimimo.com", "api_key": "k",
        "model": "mimo-v2.5-asr", "chat_path": "/v1/chat/completions", "language": "zh",
        "compat": {"auth_header": "api-key", "audio_data_url": True, "send_language": True},
    }
    client, fake = _client_with_profile(monkeypatch, prof)
    assert client._headers["api-key"] == "k"
    assert "Authorization" not in client._headers

    text = await client.transcribe_base64("QUJD", "wav")
    assert text == "你好"
    body = fake.captured["json"]
    assert fake.captured["headers"].get("api-key") == "k"
    assert "Authorization" not in fake.captured["headers"]
    audio = body["messages"][0]["content"][0]["input_audio"]
    assert audio["data"] == "data:audio/wav;base64,QUJD"  # data URL 前缀
    assert body.get("asr_options") == {"language": "zh"}  # 明确语种


@pytest.mark.asyncio
async def test_asr_default_compat_preserves_behavior(monkeypatch):
    # 无 compat → Bearer 头 + 裸 base64 + 无 asr_options（与既有行为一致）
    prof = {"provider": "openai", "endpoint": "https://x", "api_key": "k", "model": "m",
            "chat_path": "/v1/chat/completions", "language": "zh"}
    client, fake = _client_with_profile(monkeypatch, prof)
    assert client._headers["Authorization"] == "Bearer k"

    await client.transcribe_base64("QUJD", "wav")
    body = fake.captured["json"]
    assert fake.captured["headers"].get("Authorization") == "Bearer k"
    audio = body["messages"][0]["content"][0]["input_audio"]
    assert audio["data"] == "QUJD"
    assert "asr_options" not in body
