# -*- coding: utf-8 -*-
"""异步 LLM 客户端 — 重试 + 熔断 + 连接池（参照 InfiniteLogic src/llm_client.py）。Asynchronous LLM client — retry + circuit breaker + connection pool (ported from InfiniteLogic src/llm_client.py)."""
import asyncio
import random
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from core import config
from core.config import resolve_llm_profile
from core.container import AppContext
from core.llm.stream import stream_chat
from core.logger import logger


class CircuitBreakerOpenError(Exception):
    """熔断器处于 OPEN 状态时抛出。Raised when the circuit breaker is in the OPEN state."""
    pass


class RetryExhaustedError(Exception):
    """所有模型 / 所有重试均失败时抛出。Raised when all models / all retries have failed."""
    pass


class CircuitBreaker:
    """熔断器：CLOSED --N失败--> OPEN --冷却--> HALF_OPEN --3成功--> CLOSED。Circuit breaker: CLOSED --N failures--> OPEN --cooldown--> HALF_OPEN --3 successes--> CLOSED."""

    def __init__(self, failure_threshold: int = 5, cooldown_seconds: float = 30.0) -> None:
        """初始化熔断参数与内部状态。Initialize circuit breaker parameters and internal state.

        Args:
            failure_threshold: 连续失败多少次后打开熔断器。Failures needed to trip the breaker to OPEN.
            cooldown_seconds: 冷却时长，之后进入 HALF_OPEN 试探。Cooldown seconds before transitioning to HALF_OPEN probing.
        """
        self._threshold = failure_threshold
        self._cooldown = cooldown_seconds
        self._state = "CLOSED"
        self._failures = 0
        self._successes = 0
        self._opened_at = 0.0
        self._probe = False
        self._lock = asyncio.Lock()

    async def is_open(self) -> bool:
        """判断熔断器是否应拒绝新请求（含 HALF_OPEN 单探针逻辑）。Return whether new requests should be rejected (including the HALF_OPEN single-probe logic).

        Returns:
            为 True 时调用方应立即抛熔断错误。True means the caller should raise a circuit-breaker error immediately.
        """
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
        """记录一次成功：HALF_OPEN 下连续 3 次成功则恢复 CLOSED。Record a success: 3 consecutive successes in HALF_OPEN recover the breaker to CLOSED."""
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
        """记录一次失败：CLOSED 下累计达阈值即打开；HALF_OPEN 下立即重新打开。Record a failure: accumulate to the threshold in CLOSED to open; reopen immediately in HALF_OPEN."""
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
        """释放 HALF_OPEN 探针标记（请求结束无论成败都调用）。Release the HALF_OPEN probe flag (called after a request finishes regardless of outcome)."""
        async with self._lock:
            self._probe = False


_RETRYABLE = {429, 502, 503, 504}
_PERMANENT = {400, 401, 402, 403, 404, 422}


class _SwitchModel(Exception):
    """当前模型不可用（不存在/重试耗尽）→ 切换到下一个备选模型（openclaw 式 failover）。The current model is unavailable (missing / retries exhausted) → switch to the next fallback model (openclaw-style failover)."""


def _is_model_missing(exc: Exception) -> bool:
    """启发式判断「模型不存在/不可用」：4xx 且响应文本含 model → 应切备选而非重试。Heuristic for "model missing/unavailable": 4xx with 'model' in the response text → switch fallback instead of retrying."""
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (400, 404):
        return "model" in (exc.response.text or "").lower()
    return False


def _model_sequence(profile: dict) -> list[str]:
    """failover 模型序列 = [当前模型] + agent.models_failover（去重、去空）。Build the failover model sequence = [current model] + agent.models_failover (deduplicated and empty-filtered)."""
    primary = profile.get("model") or ""
    seq: list[str] = []
    for m in ([primary] + list(config.settings.agent.models_failover)):
        if m and m not in seq:
            seq.append(m)
    return seq or [primary]


def _is_retryable(exc: Exception) -> bool:
    """判断异常是否可重试：可重试状态码 / 超时 / 连接类错误为真。Decide whether an exception is retryable: retryable status codes, timeouts, and connection errors return True."""
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
    """指数退避 + 抖动（±25%）。Exponential backoff with jitter (±25%).

    Args:
        attempt: 从 1 开始的尝试序号。Attempt number starting from 1.

    Returns:
        本次重试前的等待秒数。Seconds to wait before the next retry.
    """
    base = config.settings.llm_client.retry_backoff_base
    cap = config.settings.llm_client.retry_backoff_max
    raw = min(base * (2 ** (attempt - 1)), cap)
    return max(0.0, raw + raw * 0.25 * (2 * random.random() - 1))


class LlmClient:
    """全局 LLM 客户端：连接池 + 熔断 + 多模型 failover。Global LLM client: connection pool + circuit breaker + multi-model failover."""

    def __init__(self) -> None:
        """初始化连接池引用与熔断器。Initialize the connection-pool reference and circuit breaker."""
        self._http: httpx.AsyncClient | None = None
        self._breaker = CircuitBreaker(
            failure_threshold=config.settings.llm_client.circuit_breaker_threshold,
            cooldown_seconds=config.settings.llm_client.circuit_breaker_cooldown,
        )

    async def _get_http(self) -> httpx.AsyncClient:
        """惰性创建 / 复用底层 httpx 连接池。Lazily create or reuse the underlying httpx connection pool.

        Returns:
            可复用的 AsyncClient 实例。A reusable AsyncClient instance.
        """
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                timeout=config.settings.llm_client.request_timeout,
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            )
        return self._http

    async def close(self) -> None:
        """关闭底层 httpx 连接池（AppContext.shutdown 时调用）。Close the underlying httpx connection pool (called at AppContext.shutdown)."""
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def retry_stream_chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        *,
        profile: dict | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[dict]:
        """带重试 + 熔断 + 连接池 + 模型 failover 的流式聊天。Streaming chat with retry + circuit breaker + connection pool + model failover.

        模型序列 = [当前 profile.model] + config.agent.models_failover：
        模型不存在（_is_model_missing）或重试耗尽时切下一个；已吐部分输出不切（避免重复执行）。
        全部模型失败末尾记一次熔断失败，抛 RetryExhaustedError。

        Model sequence = [current profile.model] + config.agent.models_failover:
        switch to the next one when the model is missing (_is_model_missing) or retries are exhausted;
        never switch after partial output has been emitted (to avoid re-running the task).
        When every model fails, one breaker failure is recorded and RetryExhaustedError is raised.

        temperature 非 None 时覆盖 profile 温度（结构化输出阶段调低提稳）。When temperature is not None it overrides the profile temperature (lowered to stabilize structured output).

        Args:
            messages: 对话消息列表。Conversation messages.
            tools: 可选工具定义。Optional tool definitions.
            profile: 可选 LLM profile（默认取全局配置）。Optional LLM profile (defaults to the global config).
            temperature: 可选采样温度覆盖。Optional sampling temperature override.

        Yields:
            与 stream_chat 一致的 LLM 流式事件。LLM streaming events identical to those of stream_chat.

        Raises:
            CircuitBreakerOpenError: 熔断器处于 OPEN 状态。The circuit breaker is OPEN.
            RetryExhaustedError: 所有模型均失败。All models failed.
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
                if temperature is not None:
                    prof["temperature"] = temperature
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
        """单个模型的重试循环：成功 yield 到 done；模型缺失/重试耗尽抛 _SwitchModel；已吐部分输出抛 RetryExhaustedError。Retry loop for a single model: yield until done on success; raise _SwitchModel when the model is missing or retries are exhausted; raise RetryExhaustedError after partial output has been emitted.

        Args:
            prof: 覆盖后的模型 profile（含 model / temperature）。The overridden model profile (incl. model / temperature).
            messages: 对话消息列表。Conversation messages.
            tools: 可选工具定义。Optional tool definitions.
            client: 复用的 httpx 连接。The reused httpx client.
            max_retries: 单模型最大重试次数。Max retries per model.

        Yields:
            LLM 流式事件。LLM streaming events.
        """
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


def get_llm_client() -> LlmClient:
    """返回容器持有的全局 LLM 客户端（测试可 monkeypatch 本函数）。Return the global LLM client held by the container (tests may monkeypatch this function)."""
    return AppContext.get().llm_client()
