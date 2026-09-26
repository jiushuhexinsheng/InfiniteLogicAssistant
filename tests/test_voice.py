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


# ─── 瞬时网络故障重试（实测该 ASR 服务会随机「Server disconnected」）───
# Transient network failure retries (the ASR service was measured to drop
# connections with "Server disconnected" at random).


class _FlakyClient:
    """前 N-1 次抛瞬时网络异常，最后一次成功。Fails with a transient network error
    N-1 times, then succeeds."""

    def __init__(self, failures: int, exc_factory):
        self.failures = failures
        self.exc_factory = exc_factory
        self.calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, headers=None):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.exc_factory()
        return _FakeResp()


def _profile() -> dict:
    return {"provider": "openai", "endpoint": "https://x", "api_key": "k",
            "model": "m", "chat_path": "/v1/chat/completions"}


@pytest.mark.asyncio
async def test_asr_retries_transient_disconnects_then_succeeds(monkeypatch):
    """「Server disconnected」（RemoteProtocolError）重试后成功 —— 一次抖动不丢段。
    A "Server disconnected" (RemoteProtocolError) is retried to success — one blip
    must not lose the clip."""
    import httpx

    flaky = _FlakyClient(2, lambda: httpx.RemoteProtocolError("Server disconnected without sending a response."))
    monkeypatch.setattr(voice_mod, "resolve_asr_profile", lambda: ("x", _profile()))
    monkeypatch.setattr(voice_mod.httpx, "AsyncClient", lambda *a, **kw: flaky)
    # 退避不真睡（测试提速）；只验重试次数与最终结果。Backoff is stubbed out for speed.
    async def _no_sleep(_):
        return None
    monkeypatch.setattr(voice_mod.asyncio, "sleep", _no_sleep)

    client = voice_mod.ASRClient()
    text = await client.transcribe_base64("QUJD", "wav")
    assert text == "你好"
    assert flaky.calls == 3  # 2 次失败 + 1 次成功


@pytest.mark.asyncio
async def test_asr_retry_gives_up_after_max_attempts(monkeypatch):
    """持续断连时按上限放弃并抛出原异常（不无限重试）。
    Persistent disconnects give up at the attempt limit and raise the original
    error (no infinite retries)."""
    import httpx

    flaky = _FlakyClient(99, lambda: httpx.RemoteProtocolError("Server disconnected"))
    monkeypatch.setattr(voice_mod, "resolve_asr_profile", lambda: ("x", _profile()))
    monkeypatch.setattr(voice_mod.httpx, "AsyncClient", lambda *a, **kw: flaky)

    async def _no_sleep(_):
        return None
    monkeypatch.setattr(voice_mod.asyncio, "sleep", _no_sleep)

    client = voice_mod.ASRClient()
    with pytest.raises(httpx.RemoteProtocolError):
        await client.transcribe_base64("QUJD", "wav")
    assert flaky.calls == 3  # _MAX_ATTEMPTS


@pytest.mark.asyncio
async def test_asr_does_not_retry_client_errors(monkeypatch):
    """4xx 等非瞬时错误不重试（重试无意义，立刻抛）。
    Non-transient errors (e.g. 4xx) are not retried — raise immediately."""
    flaky = _FlakyClient(99, lambda: ValueError("bad request body"))
    monkeypatch.setattr(voice_mod, "resolve_asr_profile", lambda: ("x", _profile()))
    monkeypatch.setattr(voice_mod.httpx, "AsyncClient", lambda *a, **kw: flaky)

    client = voice_mod.ASRClient()
    with pytest.raises(ValueError):
        await client.transcribe_base64("QUJD", "wav")
    assert flaky.calls == 1  # 一次都不重试。Not one retry.
