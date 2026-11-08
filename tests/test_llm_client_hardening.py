# -*- coding: utf-8 -*-
"""LLM 客户端加固（docs/designs/10 5.6）。

- 熔断器按 (provider, endpoint, model) 分桶：一个 profile 挂掉不应阻塞 judge/confirm/RAG；
- 共享 httpx client 的 timeout 按请求传入（connect/write/pool + profile read timeout）；
- HALF_OPEN 单探针在探针结束后仍然有效（并发请求不得同时放行）；
- 空模型名在调用前拒绝。

LLM-client hardening (docs/designs/10 5.6): per-profile circuit buckets, per-request
timeouts on the shared httpx client, a HALF_OPEN probe that stays exclusive after it
is released, and rejection of an empty model name before any call.
"""
import httpx
import pytest

from core import config
from core.llm import client as client_mod
from core.llm import stream as stream_mod


@pytest.mark.asyncio
async def test_breaker_is_per_profile(monkeypatch):
    """一个 profile 的熔断不阻塞另一个 profile。"""
    from types import SimpleNamespace
    monkeypatch.setattr(config.settings.llm_client, "retry_max", 0)
    monkeypatch.setattr(config.settings.llm_client, "circuit_breaker_threshold", 1)
    monkeypatch.setattr(config.settings.llm_client, "circuit_breaker_cooldown", 3600)
    monkeypatch.setattr(config.settings.agent, "models_failover", [])
    monkeypatch.setattr(client_mod, "_is_retryable", lambda exc: True)

    async def boom(messages, tools=None, *, profile=None, client=None, timeout=None):
        raise RuntimeError("endpoint down")
        yield  # pragma: no cover

    monkeypatch.setattr(client_mod, "stream_chat", boom)
    c = client_mod.LlmClient()
    a = {"provider": "openai", "endpoint": "https://a", "model": "m1"}
    b = {"provider": "openai", "endpoint": "https://b", "model": "m2"}
    try:
        with pytest.raises(client_mod.RetryExhaustedError):
            async for _ in c.retry_stream_chat([], profile=a):
                pass
        # A 已熔断。
        with pytest.raises(client_mod.CircuitBreakerOpenError):
            async for _ in c.retry_stream_chat([], profile=a):
                pass
        # B 是另一个分桶：仍进入调用（失败类型是 RetryExhausted，不是熔断）。
        with pytest.raises(client_mod.RetryExhaustedError):
            async for _ in c.retry_stream_chat([], profile=b):
                pass
    finally:
        await c.close()


@pytest.mark.asyncio
async def test_per_request_timeout_from_profile(monkeypatch):
    """每次调用按 profile.timeout 生成 httpx.Timeout（connect/write/pool 固定短超时）。"""
    seen: dict = {}

    async def fake_stream(messages, tools=None, *, profile=None, client=None, timeout=None):
        seen["timeout"] = timeout
        yield {"type": "done", "message": {}}

    monkeypatch.setattr(client_mod, "stream_chat", fake_stream)
    c = client_mod.LlmClient()
    try:
        profile = {"provider": "openai", "endpoint": "https://e", "model": "m", "timeout": 7}
        async for _ in c.retry_stream_chat([], profile=profile):
            pass
    finally:
        await c.close()

    t = seen["timeout"]
    assert isinstance(t, httpx.Timeout)
    assert t.read == 7
    assert t.connect == 10
    assert t.write == 10
    assert t.pool == 10


@pytest.mark.asyncio
async def test_stream_chat_forwards_timeout(monkeypatch):
    """stream_chat 把 timeout 透传给协议层（协议层再交给 client.stream）。"""
    sentinel = httpx.Timeout(3.0)
    seen: dict = {}

    async def fake_openai(messages, tools, profile, client, timeout=None):
        seen["timeout"] = timeout
        yield {"type": "done", "message": {}}

    monkeypatch.setattr(stream_mod, "_stream_openai", fake_openai)
    monkeypatch.setattr(stream_mod, "resolve_protocol", lambda p: "openai")

    async for _ in stream_mod.stream_chat([], profile={"model": "m"}, timeout=sentinel):
        pass
    assert seen["timeout"] is sentinel


@pytest.mark.asyncio
async def test_half_open_probe_stays_exclusive():
    """HALF_OPEN 每次只放行一个探针，探针释放后下一个才接上。"""
    cb = client_mod.CircuitBreaker(failure_threshold=1, cooldown_seconds=0)
    await cb.record_failure()          # → OPEN
    assert await cb.is_open() is False  # OPEN → HALF_OPEN，领取探针
    assert await cb.is_open() is True   # 并发请求被拒
    await cb.release_probe()
    assert await cb.is_open() is False  # 下一个探针
    assert await cb.is_open() is True   # 它同样独占（回归：旧实现这里会放行无限并发）


@pytest.mark.asyncio
async def test_empty_model_rejected_before_call(monkeypatch):
    """空模型名在发起请求前拒绝，不发一次注定失败的调用。"""
    called: list[int] = []

    async def fake_stream(messages, tools=None, *, profile=None, client=None, timeout=None):
        called.append(1)
        yield {"type": "done", "message": {}}

    monkeypatch.setattr(client_mod, "stream_chat", fake_stream)
    c = client_mod.LlmClient()
    try:
        with pytest.raises(ValueError):
            async for _ in c.retry_stream_chat(
                [], profile={"provider": "openai", "endpoint": "https://e", "model": ""},
            ):
                pass
    finally:
        await c.close()
    assert called == []
