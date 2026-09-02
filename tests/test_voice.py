# -*- coding: utf-8 -*-
"""core/voice — ASR 客户端 compat 兼容开关（小米 MiMo ASR：api-key 头 / data URL 前缀 / asr_options）。
core/voice — ASR client compat switches (Xiaomi MiMo ASR: api-key header / data URL prefix / asr_options).
"""
import pytest

import core.voice as voice_mod


class _FakeResp:
    """测试用的假响应：模拟成功响应并返回固定文本。
    A fake response for tests: simulates a successful response returning fixed text.
    """
    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": "你好"}}]}


class _FakeClient:
    """测试用的假 HTTP 客户端：记录最后一次请求并返回假响应。
    A fake HTTP client for tests: records the last request and returns a fake response.
    """
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
    """测试 compat 开关：api-key 头、data URL 前缀与 asr_options 语种。Tests the compat switches: api-key header, data URL prefix, and asr_options language."""
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


def test_asr_empty_chat_path_falls_back_to_default(monkeypatch):
    """测试空 chat_path 回退到默认路径。Tests an empty chat_path falling back to the default path."""
    # 空 chat_path 必须回退默认，否则会请求裸 endpoint（如 .../v1）→ 404
    prof = {"provider": "openai", "endpoint": "https://api.xiaomimimo.com", "api_key": "k", "model": "m", "chat_path": ""}
    client, _ = _client_with_profile(monkeypatch, prof)
    assert client.chat_path == "/v1/chat/completions"


@pytest.mark.asyncio
async def test_asr_default_compat_preserves_behavior(monkeypatch):
    """测试无 compat 配置时保持默认行为（Bearer 头与裸 base64）。Tests default behavior (Bearer header and raw base64) being preserved without compat config."""
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
