# -*- coding: utf-8 -*-
"""ReAct Agent 循环 — 原生 OpenAI function-calling（参照 InfiniteLogic src/agent.py）

流程: 调 LLM(tools) → 有 tool_calls 则执行并回喂 → 直到最终答案
事件: content_delta / reasoning_delta / tool_start / tool_end / done / error
"""
import json
from collections.abc import AsyncIterator
from typing import Any

from core.config import cfg
from core.llm.client import CircuitBreakerOpenError, RetryExhaustedError, get_llm_client
from core.logger import logger
from core.tools import TOOLS


def _trim_history(messages: list[dict], max_messages: int) -> list[dict]:
    """保留前导 system + 最近 N 条；不切断 tool_call↔tool 配对。"""
    if len(messages) <= max_messages:
        return messages
    system: list[dict] = []
    rest: list[dict] = []
    for m in messages:
        if m.get("role") == "system" and not rest:
            system.append(m)
        else:
            rest.append(m)
    keep = max(1, max_messages - len(system))
    tail = rest[-keep:]
    while tail and tail[0].get("role") == "tool":
        tail.pop(0)
    return system + tail


async def run_agent(messages: list[dict], tools: list[dict] | None = None) -> AsyncIterator[dict]:
    """ReAct 循环：LLM(tools) → 执行 tool_calls → 回喂 → 直到最终答案。"""
    history = list(messages)
    recursion_limit = cfg("agent.recursion_limit", 6)
    max_history = cfg("agent.max_history_messages", 40)

    for step in range(recursion_limit):
        try:
            assistant_message: dict | None = None
            async for event in get_llm_client().retry_stream_chat(
                _trim_history(history, max_history), tools=tools or TOOLS.schemas()
            ):
                etype = event["type"]
                if etype == "reasoning_delta":
                    yield {"type": "reasoning_delta", "text": event["text"]}
                elif etype == "content_delta":
                    yield {"type": "content_delta", "text": event["text"]}
                elif etype == "tool_call_delta":
                    pass  # UI 等完整 tool_start / tool_end
                elif etype == "done":
                    assistant_message = event["message"]
        except CircuitBreakerOpenError:
            yield {"type": "error", "message": "服务暂时不可用，请稍后重试"}
            return
        except RetryExhaustedError as exc:
            logger.error("LLM retries exhausted: {}", exc)
            yield {"type": "error", "message": f"LLM 调用失败: {exc}"}
            return
        except Exception as exc:
            logger.error("LLM call failed: {}", exc)
            yield {"type": "error", "message": f"LLM 调用失败: {exc}"}
            return

        if assistant_message is None:
            yield {"type": "error", "message": "LLM 返回空消息"}
            return

        history.append(assistant_message)
        tool_calls = assistant_message.get("tool_calls") or []
        if not tool_calls:
            yield {"type": "done"}
            return

        # 执行工具调用（串行）
        for tc in tool_calls:
            name = tc["function"]["name"]
            raw = tc["function"].get("arguments") or "{}"
            try:
                args = json.loads(raw) if isinstance(raw, str) else raw
            except json.JSONDecodeError:
                args = {}
            yield {"type": "tool_start", "name": name, "args": args}
            logger.info("tool_call step={} name={} args={}", step, name, args)
            result = await TOOLS.acall(name, args)
            status = "error" if result.startswith("Error") else "ok"
            yield {"type": "tool_end", "name": name, "status": status, "output": result}
            history.append({"role": "tool", "tool_call_id": tc.get("id", ""), "content": result})

    yield {"type": "error", "message": f"工具循环超出上限（{recursion_limit} 步）"}
