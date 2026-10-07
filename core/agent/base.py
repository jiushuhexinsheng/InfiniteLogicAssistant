# -*- coding: utf-8 -*-
"""子代理基座 — 一次带角色提示词的 ReAct 循环，可取消

Sub-agent base — a single ReAct loop with a role prompt, cancellable.
"""
import asyncio
import json
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from core import config
from core.llm.client import get_llm_client
from core.logger import logger
from core.orchestrator.control import CancellationToken
from core.orchestrator.blocks import PREVIEW_LEN, llm_tool_feed
from core.orchestrator.condense import maybe_condense
from core.orchestrator.confirm import ConfirmResult
from core.orchestrator.events import ToolEndEvent, ToolStartEvent
from core.prompts import UNTRUSTED_DATA_NOTE
from core.tools.base import TOOLS
from core.tools.policy import decide


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
    confirm: Callable[[str, dict], Awaitable[ConfirmResult | bool]] | None = None,
    events: asyncio.Queue | None = None,
    agent: str = "",
) -> SubAgentResult:
    """执行子任务：LLM 循环（可调工具），直到给出结论或步数/取消。

    confirm(name, args)：非 read 工具调用前的确认回调；None 表示无确认通道 → 直接拒绝非 read 工具。
    events 非空时流式发射 tool_start/tool_end（与主 ReAct 路径一致，前端可见子代理工具时间轴）。
    agent 随工具事件下发（如 sub:searcher），前端可据此显示事件归属徽章。

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
        agent: 事件归属标识（如 ``sub:searcher``），随工具事件下发。
               Ownership label for events (e.g. ``sub:searcher``).
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
        # 滚动压缩（docs/designs/08 批2）：子代理步数更长、收益更大；失败原样返回。
        # Rolling condenser (docs/designs/08 batch 2): sub-agents run longer steps and
        # benefit most; failures return the input unchanged.
        try:
            history, omitted = await maybe_condense(
                history,
                threshold_chars=config.settings.agent.condense_threshold_chars,
            )
            if omitted:
                logger.debug("subagent 上下文已压缩（省略 {} 条）", omitted)
        except Exception:
            pass
        try:
            msg = None
            # 渐进式 schema（docs/designs/08 批4）：与主 ReAct 同口径。
            # Progressive schemas (docs/designs/08 batch 4): same convention as the main ReAct.
            async for evt in get_llm_client().retry_stream_chat(
                    history, tools=TOOLS.schemas(stub_groups=config.settings.tools.lazy_groups)):
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
            call_id = tc.get("id", "")
            raw = tc["function"].get("arguments") or "{}"
            try:
                args = json.loads(raw) if isinstance(raw, str) else raw
            except json.JSONDecodeError:
                args = {}
            if events is not None:
                await events.put(ToolStartEvent(name=name, args=args, call_id=call_id,
                                                agent=agent or None).emit())
            # 工具调用走权限策略（与主 ReAct 路径一致）：allow 直放 / deny 直接拒绝 /
            # ask 需操作者确认，无确认通道时一律拒绝。
            # Tool calls go through the permission policy (consistent with the main ReAct
            # path): allow runs, deny is refused, ask needs operator confirmation and is
            # refused when no confirmation channel exists.
            decision = decide(name)
            if decision.action == "allow":
                result = await TOOLS.acall(name, args, cancel=cancel)
            elif decision.action == "deny":
                result = f"Error: 操作者策略禁止调用 {name}（{decision.source}）"
            elif confirm is None:
                result = f"Error: 工具 {name} 需要操作者确认，但当前无确认通道，已拒绝"
            else:
                conf = await confirm(name, args)
                if conf:
                    result = await TOOLS.acall(name, args, cancel=cancel)
                else:
                    # 拒绝理由回喂子代理 LLM 作为纠偏信号（getattr 兼容测试桩返回裸 bool）。
                    # The refusal rationale is fed back to the sub-agent LLM as a
                    # corrective signal (getattr keeps plain-bool test doubles working).
                    result = f"Error: 操作者拒绝调用 {name}"
                    reason = getattr(conf, "reason", "") or ""
                    if reason:
                        result += f"（理由：{reason[:200]}）"
                    result += "。请调整方案、换用其他工具，或先向用户说明后再请求。"
            if events is not None:
                status = "error" if result.startswith("Error") else "ok"
                await events.put(ToolEndEvent(
                    name=name, status=status, output=result[:PREVIEW_LEN],
                    call_id=call_id, agent=agent or None,
                    truncated=len(result) > PREVIEW_LEN, output_len=len(result),
                ).emit())
            used.append(name)
            # LLM 口径（docs/designs/08 批1）：正文按 tools.llm_max_output_chars 截断；
            # 事件/审计仍发原文（上方 ToolEnd 已带）。
            # LLM-side convention (docs/designs/08 batch 1): the body is capped by
            # tools.llm_max_output_chars; events/audit still carry the raw text.
            history.append({"role": "tool", "tool_call_id": call_id,
                            "content": llm_tool_feed(result)})
    return SubAgentResult("failed", f"超出步数上限（{max_steps}）", used)
