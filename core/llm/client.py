# -*- coding: utf-8 -*-
"""异步 LLM 客户端 — 重试 + 熔断 + 连接池（参照 InfiniteLogic src/llm_client.py）"""
import asyncio
import random
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from core.config import cfg
from core.llm.stream import stream_chat
from core.logger import logger


class CircuitBreakerOpenError(Exception):
    pass


class RetryExhaustedError(Exception):
    pass


class CircuitBreaker:
    """熔断器：CLOSED --N失败--> OPEN --冷却--> HALF_OPEN --3成功--> CLOSED"""

    def __init__(self, failure_threshold: int = 5, cooldown_seconds: float = 30.0) -> None:
        self._threshold = failure_threshold
        self._cooldown = cooldown_seconds
        self._state = "CLOSED"
        self._failures = 0
        self._successes = 0
        self._opened_at = 0.0
        self._probe = False
        self._lock = asyncio.Lock()

    async def is_open(self) -> bool:
        async with self._lock:
            if self._state == "HALF_OPEN" and self._probe:
                return True
            if self._state != "OPEN":
                return False
            if time.monotonic() - self._opened_at >= self._cooldown:
                self._state = "HALF_OPEN"
                self._successes = 0
                self._probe = True
                return False
            return True

    async def record_success(self) -> None:
        async with self._lock:
            self._probe = False
            if self._state == "HALF_OPEN":
                self._successes += 1
                if self._successes >= 3:
                    self._state = "CLOSED"
                    self._failures = 0
            else:
                self._failures = 0

    async def record_failure(self) -> None:
        async with self._lock:
            self._probe = False
            if self._state == "HALF_OPEN":
                self._state = "OPEN"
                self._opened_at = time.monotonic()
                self._successes = 0
            elif self._state == "CLOSED":
                self._failures += 1
                if self._failures >= self._threshold:
                    self._state = "OPEN"
                    self._opened_at = time.monotonic()

    async def release_probe(self) -> None:
        async with self._lock:
            self._probe = False


_RETRYABLE = {429, 502, 503, 504}
_PERMANENT = {400, 401, 402, 403, 404, 422}


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in _RETRYABLE:
            return True
        if code in _PERMANENT:
            return False
        return code >= 500
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError, httpx.ReadError)):
        return True
    return False


def _backoff(attempt: int) -> float:
    base = cfg("llm_client.retry_backoff_base", 0.5)
    cap = cfg("llm_client.retry_backoff_max", 10.0)
    raw = min(base * (2 ** (attempt - 1)), cap)
    return max(0.0, raw + raw * 0.25 * (2 * random.random() - 1))


class LlmClient:
    def __init__(self) -> None:
        self._http: httpx.AsyncClient | None = None
        self._breaker = CircuitBreaker(
            failure_threshold=cfg("llm_client.circuit_breaker_threshold", 5),
            cooldown_seconds=cfg("llm_client.circuit_breaker_cooldown", 30.0),
        )

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                timeout=cfg("llm_client.request_timeout", 60),
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            )
        return self._http

    async def retry_stream_chat(self, messages: list[dict], tools: list[dict] | None = None) -> AsyncIterator[dict]:
        """带重试 + 熔断 + 连接池的流式聊天。"""
        if await self._breaker.is_open():
            raise CircuitBreakerOpenError("Circuit breaker is OPEN")
        max_retries = cfg("llm_client.retry_max", 3)
        client = await self._get_http()
        emitted = False
        last_exc: Exception | None = None
        try:
            for attempt in range(max_retries + 1):
                try:
                    async for event in stream_chat(messages, tools, client=client):
                        if event["type"] in ("content_delta", "reasoning_delta", "tool_call_delta"):
                            emitted = True
                        yield event
                        if event["type"] == "done":
                            await self._breaker.record_success()
                            return
                except Exception as exc:
                    last_exc = exc
                    if not _is_retryable(exc):
                        raise
                    if emitted:
                        await self._breaker.record_failure()
                        raise RetryExhaustedError(f"LLM stream failed after partial output: {exc}") from exc
                    if attempt >= max_retries:
                        await self._breaker.record_failure()
                        raise RetryExhaustedError(f"LLM call failed after {max_retries} retries: {exc}") from exc
                    wait = _backoff(attempt + 1)
                    logger.warning("LLM retry in {:.1f}s (attempt {}/{}): {}", wait, attempt + 1, max_retries, exc)
                    await asyncio.sleep(wait)
            raise RetryExhaustedError(f"LLM call failed: {last_exc}")
        finally:
            await self._breaker.release_probe()


_client: LlmClient | None = None


def get_llm_client() -> LlmClient:
    global _client
    if _client is None:
        _client = LlmClient()
    return _client
