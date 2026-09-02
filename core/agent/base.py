# -*- coding: utf-8 -*-
"""子代理基座 — 一次带角色提示词的 ReAct 循环，可取消

Sub-agent base — a single ReAct loop with a role prompt, cancellable.
"""
import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from core import config
from core.llm.client import get_llm_client
from core.logger import logger
from core.orchestrator.control import CancellationToken
from core.orchestrator.events import ToolEndEvent, ToolStartEvent
from core.prompts import UNTRUSTED_DATA_NOTE
from core.tools.base import TOOLS


@dataclass
class SubAgentResult:
    """子代理执行结果。

    Sub-agent execution result.

    Attributes:
        status: 执行状态，done / failed / stopped。
               Execution status: ``done`` / ``failed`` / ``stopped``.
        output: 子代理的最终输出文本。
                Final output text from the sub-agent.
        used_tools: 本次执行中调用过的工具名称列表。
                    List of tool names invoked during this execution.
    """

    status: str  # done / failed / stopped
    output: str
    used_tools: list[str] = field(default_factory=list)


async def run_subagent(
    role_prompt: str,
    goal: str,
    context: str = "",
    cancel: CancellationToken | None = None,
    max_steps: int | None = None,
    confirm: Callable[[str, dict], Awaitable[bool]] | None = None,
    events: asyncio.Queue | None = None,
) -> SubAgentResult:
    """执行子任务：LLM 循环（可调工具），直到给出结论或步数/取消。

    confirm(name, args)：非 read 工具调用前的确认回调；None 表示无确认通道 → 直接拒绝非 read 工具。
    events 非空时流式发射 tool_start/tool_end（与主 ReAct 路径一致，前端可见子代理工具时间轴）。

    Execute a sub-task: an LLM loop (with tool-calling) that runs until a
    conclusion is produced, the step limit is reached, or cancellation is
    signalled.

    Args:
        role_prompt: 角色提示词。
                     Role prompt for the sub-agent.
        goal: 子任务目标描述。
              Sub-task goal description.
        context: 可选的背景上下文（RAG/记忆注入）。
                 Optional background context (RAG / memory injection).
        cancel: 可选的取消令牌。
                Optional cancellation token.
        max_steps: 最大执行步数，默认取 config 中的 recursion_limit。
                   Max execution steps; defaults to ``config.settings.agent.recursion_limit``.
        confirm: 非 read 工具调用前的确认回调；``None`` 表示无确认通道，直接拒绝非 read 工具。
                 Confirmation callback for non-read tool calls; ``None`` means
                 no confirmation channel, rejecting all non-read tools.
        events: 非空时流式发射 tool_start / tool_end 事件（前端可见子代理工具时间轴）。
                When provided, emits ``tool_start`` / ``tool_end`` events
                (visible in the front-end timeline).
    """
    max_steps = max_steps or config.settings.agent.recursion_limit
    history = [
        {"role": "system", "content": f"{role_prompt}\n\n{UNTRUSTED_DATA_NOTE}"},
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
            if events is not None:
                await events.put(ToolStartEvent(name=name, args=args).emit())
            # 非 read 工具需操作者确认；无确认通道时一律拒绝（与主 ReAct 路径一致）
            risk = TOOLS.risk(name)
            if risk == "read":
                result = await TOOLS.acall(name, args, cancel=cancel)
            elif confirm is None:
                result = f"Error: 工具 {name} 需要操作者确认，但当前无确认通道，已拒绝"
            elif await confirm(name, args):
                result = await TOOLS.acall(name, args, cancel=cancel)
            else:
                result = f"Error: 操作者拒绝调用 {name}"
            if events is not None:
                status = "error" if result.startswith("Error") else "ok"
                await events.put(ToolEndEvent(name=name, status=status, output=result[:500]).emit())
            used.append(name)
            history.append({"role": "tool", "tool_call_id": tc.get("id", ""), "content": result})
    return SubAgentResult("failed", f"超出步数上限（{max_steps}）", used)
