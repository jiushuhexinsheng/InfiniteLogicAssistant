# -*- coding: utf-8 -*-
"""core/llm/client.py — 熔断器状态机 + 重试分类 + 重试流逻辑"""
import json
import time

import httpx
import pytest

from core.llm.client import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    LlmClient,
    RetryExhaustedError,
    _backoff,
    _is_retryable,
)


def _sse(chunks) -> bytes:
    lines = [f"data: {json.dumps(c, ensure_ascii=False)}" for c in chunks]
    lines.append("data: [DONE]")
    return ("\n\n".join(lines) + "\n\n").encode("utf-8")


# ─── 熔断器状态机 ───

@pytest.mark.asyncio
async def test_breaker_closed_to_open_after_threshold():
    cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=30)
    assert await cb.is_open() is False
    for _ in range(3):
        await cb.record_failure()
    assert await cb.is_open() is True


@pytest.mark.asyncio
async def test_breaker_half_open_after_cooldown_then_closes():
    cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=30)
    await cb.record_failure()
    await cb.record_failure()
    assert await cb.is_open() is True  # 冷却期未过 → 拒绝
    # 拨动开启时刻到冷却期之前 → 下一次调用进入 HALF_OPEN，放行单个探测
    cb._opened_at = time.monotonic() - 31
    assert await cb.is_open() is False
    # 探测占用期间并发请求被拒
    assert await cb.is_open() is True
    # 连续 3 次成功 → 恢复 CLOSED
    for _ in range(3):
        await cb.record_success()
    assert await cb.is_open() is False


@pytest.mark.asyncio
async def test_breaker_half_open_failure_reopens():
    cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=30)
    await cb.record_failure()
    await cb.record_failure()
    cb._opened_at = time.monotonic() - 31
    await cb.is_open()  # → HALF_OPEN
    await cb.record_failure()  # 探测失败 → 回到 OPEN
    assert await cb.is_open() is True


# ─── 重试分类 ───

def test_is_retryable_classifies_status():
    def status_error(code: int) -> httpx.HTTPStatusError:
        return httpx.HTTPStatusError(
            "boom", request=httpx.Request("POST", "http://t"), response=httpx.Response(code)
        )

    assert _is_retryable(status_error(429)) is True
    assert _is_retryable(status_error(502)) is True
    assert _is_retryable(status_error(503)) is True
    assert _is_retryable(status_error(500)) is True
    assert _is_retryable(status_error(400)) is False
    assert _is_retryable(status_error(401)) is False
    assert _is_retryable(status_error(404)) is False
    assert _is_retryable(httpx.TimeoutException("t")) is True
    assert _is_retryable(httpx.ConnectError("c")) is True
    assert _is_retryable(ValueError("other")) is False


def test_backoff_increases_and_capped():
    a, b = _backoff(1), _backoff(2)
    assert 0 <= a < b
    assert _backoff(20) <= 10.0 * 1.25  # 受 cap=10 + 25% jitter 约束


# ─── retry_stream_chat ───

@pytest.mark.asyncio
async def test_retry_stream_chat_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr("core.llm.client._backoff", lambda attempt: 0)
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, content=b"", headers={"Content-Type": "text/event-stream"})
        return httpx.Response(200, content=_sse([{"choices": [{"delta": {"content": "ok"}}]}]))

    client = LlmClient()
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        events = [e async for e in client.retry_stream_chat([])]
        assert calls["n"] == 2
        assert events[-1]["type"] == "done"
        assert events[0]["type"] == "content_delta"
    finally:
        await client._http.aclose()


@pytest.mark.asyncio
async def test_retry_stream_chat_no_retry_after_partial_output(monkeypatch):
    calls = {"n": 0}

    async def fake_stream_chat(messages, tools=None, client=None):
        calls["n"] += 1
        yield {"type": "content_delta", "text": "部分"}
        raise httpx.ReadError("connection reset")

    monkeypatch.setattr("core.llm.client.stream_chat", fake_stream_chat)
    monkeypatch.setattr("core.llm.client._backoff", lambda attempt: 0)

    client = LlmClient()
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    events = []
    try:
        with pytest.raises(RetryExhaustedError):
            async for e in client.retry_stream_chat([]):
                events.append(e)
        assert any(e["type"] == "content_delta" for e in events)
        assert calls["n"] == 1  # 已发出部分内容 → 不重试（避免重复）
    finally:
        await client._http.aclose()


@pytest.mark.asyncio
async def test_retry_stream_chat_permanent_error_no_retry(monkeypatch):
    monkeypatch.setattr("core.llm.client._backoff", lambda attempt: 0)
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(401, content=b"", headers={"Content-Type": "text/event-stream"})

    client = LlmClient()
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(httpx.HTTPStatusError):
            async for _ in client.retry_stream_chat([]):
                pass
        assert calls["n"] == 1  # 永久错误不重试
    finally:
        await client._http.aclose()


@pytest.mark.asyncio
async def test_retry_stream_chat_breaker_open_raises():
    client = LlmClient()
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    try:
        for _ in range(client._breaker._threshold):
            await client._breaker.record_failure()
        with pytest.raises(CircuitBreakerOpenError):
            async for _ in client.retry_stream_chat([]):
                pass
    finally:
        await client._http.aclose()
