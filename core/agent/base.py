# -*- coding: utf-8 -*-
"""子代理基座 — 一次带角色提示词的 ReAct 循环，可取消"""
import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from core.config import cfg
from core.llm.client import get_llm_client
from core.logger import logger
from core.orchestrator.control import CancellationToken
from core.tools.base import TOOLS


@dataclass
class SubAgentResult:
    status: str  # done / failed / stopped
    output: str
    used_tools: list[str] = field(default_factory=list)


async def run_subagent(
    role_prompt: str,
    goal: str,
    context: str = "",
    cancel: CancellationToken | None = None,
    max_steps: int | None = None,
) -> SubAgentResult:
    """执行子任务：LLM 循环（可调工具），直到给出结论或步数/取消。"""
    max_steps = max_steps or cfg("agent.recursion_limit", 12)
    history = [
        {"role": "system", "content": role_prompt},
        {"role": "user", "content": f"子任务目标：{goal}\n背景：{context or '（无）'}"},
    ]
    used: list[str] = []
    for _ in range(max_steps):
        if cancel is not None and cancel.is_cancelled:
            return SubAgentResult("stopped", "已停止", used)
        try:
            msg = None
            async for evt in get_llm_client().retry_stream_chat(history, tools=TOOLS.schemas()):
                if evt["type"] == "done":
                    msg = evt["message"]
        except asyncio.CancelledError:
            return SubAgentResult("stopped", "已停止", used)
        except Exception as e:
            logger.warning("subagent LLM 调用失败: {}", e)
            return SubAgentResult("failed", f"LLM 调用失败: {e}", used)
        if msg is None:
            return SubAgentResult("failed", "LLM 返回空消息", used)
        history.append(msg)
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            return SubAgentResult("done", msg.get("content") or "完成", used)
        for tc in tool_calls:
            if cancel is not None and cancel.is_cancelled:
                return SubAgentResult("stopped", "已停止", used)
            name = tc["function"]["name"]
            raw = tc["function"].get("arguments") or "{}"
            try:
                args = json.loads(raw) if isinstance(raw, str) else raw
            except json.JSONDecodeError:
                args = {}
            result = await TOOLS.acall(name, args)
            used.append(name)
            history.append({"role": "tool", "tool_call_id": tc.get("id", ""), "content": result})
    return SubAgentResult("failed", f"超出步数上限（{max_steps}）", used)
