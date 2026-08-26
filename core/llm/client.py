# -*- coding: utf-8 -*-
"""异步 LLM 客户端 — 重试 + 熔断 + 连接池（参照 InfiniteLogic src/llm_client.py）"""
import asyncio
import random
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from core import config
from core.config import resolve_llm_profile
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


class _SwitchModel(Exception):
    """当前模型不可用（不存在/重试耗尽）→ 切换到下一个备选模型（openclaw 式 failover）。"""


def _is_model_missing(exc: Exception) -> bool:
    """启发式判断「模型不存在/不可用」：4xx 且响应文本含 model → 应切备选而非重试。"""
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (400, 404):
        return "model" in (exc.response.text or "").lower()
    return False


def _model_sequence(profile: dict) -> list[str]:
    """failover 模型序列 = [当前模型] + agent.models_failover（去重、去空）。"""
    primary = profile.get("model") or ""
    seq: list[str] = []
    for m in ([primary] + list(config.settings.agent.models_failover)):
        if m and m not in seq:
            seq.append(m)
    return seq or [primary]


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
    base = config.settings.llm_client.retry_backoff_base
    cap = config.settings.llm_client.retry_backoff_max
    raw = min(base * (2 ** (attempt - 1)), cap)
    return max(0.0, raw + raw * 0.25 * (2 * random.random() - 1))


class LlmClient:
    def __init__(self) -> None:
        self._http: httpx.AsyncClient | None = None
        self._breaker = CircuitBreaker(
            failure_threshold=config.settings.llm_client.circuit_breaker_threshold,
            cooldown_seconds=config.settings.llm_client.circuit_breaker_cooldown,
        )

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                timeout=config.settings.llm_client.request_timeout,
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            )
        return self._http

    async def retry_stream_chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        *,
        profile: dict | None = None,
    ) -> AsyncIterator[dict]:
        """带重试 + 熔断 + 连接池 + 模型 failover 的流式聊天。

        模型序列 = [当前 profile.model] + config.agent.models_failover：
        模型不存在（_is_model_missing）或重试耗尽时切下一个；已吐部分输出不切（避免重复执行）。
        全部模型失败末尾记一次熔断失败，抛 RetryExhaustedError。
        """
        if await self._breaker.is_open():
            raise CircuitBreakerOpenError("Circuit breaker is OPEN")
        max_retries = config.settings.llm_client.retry_max
        client = await self._get_http()
        if profile is None:
            _, profile = resolve_llm_profile()
        models = _model_sequence(profile)
        try:
            for i, model in enumerate(models):
                prof = dict(profile)
                prof["model"] = model
                try:
                    async for event in self._attempt_model(prof, messages, tools, client, max_retries):
                        yield event
                    return  # done
                except _SwitchModel:
                    if i == len(models) - 1:
                        await self._breaker.record_failure()
                        raise RetryExhaustedError(f"LLM call failed for all models: {model}") from None
                    logger.warning("LLM 模型 {} 不可用，切换备选: {}", model, models[i + 1])
        finally:
            await self._breaker.release_probe()

    async def _attempt_model(
        self,
        prof: dict,
        messages: list[dict],
        tools: list[dict] | None,
        client: httpx.AsyncClient,
        max_retries: int,
    ) -> AsyncIterator[dict]:
        """单个模型的重试循环：成功 yield 到 done；模型缺失/重试耗尽抛 _SwitchModel；已吐部分输出抛 RetryExhaustedError。"""
        emitted = False
        for attempt in range(max_retries + 1):
            try:
                async for event in stream_chat(messages, tools, profile=prof, client=client):
                    if event["type"] in ("content_delta", "reasoning_delta", "tool_call_delta"):
                        emitted = True
                    yield event
                    if event["type"] == "done":
                        await self._breaker.record_success()
                        return
            except Exception as exc:
                if emitted:
                    # 已发出部分内容 → 不重试、不切模型（避免重复执行任务）
                    await self._breaker.record_failure()
                    raise RetryExhaustedError(f"LLM stream failed after partial output: {exc}") from exc
                if _is_model_missing(exc):
                    raise _SwitchModel() from exc
                if not _is_retryable(exc):
                    raise
                if attempt >= max_retries:
                    raise _SwitchModel() from exc
                wait = _backoff(attempt + 1)
                logger.warning("LLM retry in {:.1f}s (attempt {}/{}): {}", wait, attempt + 1, max_retries, exc)
                await asyncio.sleep(wait)
        raise _SwitchModel()  # 防御：attempt 循环耗尽（正常不会到这）


_client: LlmClient | None = None


def get_llm_client() -> LlmClient:
    global _client
    if _client is None:
        _client = LlmClient()
    return _client
