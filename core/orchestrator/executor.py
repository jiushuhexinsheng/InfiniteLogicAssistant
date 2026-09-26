# -*- coding: utf-8 -*-
"""执行循环 — plan → act(调工具) → observe(回喂) → reflect，可取消、可收敛

高风险工具（risk != read）在调用前经 confirm_if_needed 确认。
取消（CancelledError）统一收敛为 status=stopped 返回，调用方无需捕获。

Execution loop — plan → act (call tools) → observe (feed back) → reflect;
cancellable and convergent. High-risk tools (risk != read) are confirmed via
confirm_if_needed before being called. Cancellation (CancelledError) is uniformly
converged into a status=stopped result, so callers do not need to catch it.
"""
import asyncio
import json

from core.agent.coordinator import run_coordinator
from core import config
from core.llm.client import get_llm_client
from core.logger import logger
from core.memory.context import build_context
from core.orchestrator.blocks import HISTORY_LEN, PREVIEW_LEN, make_block
from core.orchestrator.confirm import confirm_tool
from core.orchestrator.control import CancellationToken
from core.orchestrator.events import ContentDeltaEvent, ToolEndEvent, ToolStartEvent, from_llm_event
from core.orchestrator.session import Session
from core.orchestrator.task import Task
from core.tools import TOOLS
from core.tools.policy import decide

from core.prompts import EXECUTOR_SYSTEM as _SYSTEM, UNTRUSTED_DATA_NOTE


def should_use_multi_agent(task: Task) -> bool:
    """复杂任务（启用多智能体且多参数/长目标）转协调者。

    Route complex tasks (multi-agent enabled and multi-param or long goal) to the
    coordinator.
    """
    return config.settings.agent.multi_agent and (len(task.params) >= 2 or len(task.goal) > 30)


async def execute_task(task: Task, session: Session, cancel: CancellationToken,
                       events: asyncio.Queue | None = None) -> dict:
    """执行任务：复杂任务转多智能体协调者；简单任务走 ReAct。

    events 非空时流式发射 tool_start/tool_end/usage/content_delta（SSE 实时呈现）。
    返回 {status: done|failed|stopped, summary, steps:[...]}。

    Execute the task: complex tasks go to the multi-agent coordinator; simple
    tasks run a ReAct loop. When events is not None,
    tool_start/tool_end/usage/content_delta are streamed (real-time SSE
    rendering). Returns {status: done|failed|stopped, summary, steps:[...]}.
    """
    if cancel.is_cancelled:
        return {"status": "stopped", "summary": "已停止", "steps": []}

    # 复杂任务 → 多智能体
    if should_use_multi_agent(task):
        cr = await run_coordinator(task, session, cancel, events)
        steps = [
            {"step": i, "tool": f"agent:{x['agent_type']}", "status": x["status"], "result": x["output"]}
            for i, x in enumerate(cr["subtasks"])
        ]
        summary = cr["summary"]
        # 把最终摘要按 content_delta 流式返回（前端累积 → 语音播报真实结论）
        if events is not None and summary:
            for i in range(0, len(summary), 200):
                await events.put(ContentDeltaEvent(text=summary[i:i + 200]).emit())
        session.append("assistant", summary)
        return {"status": cr["status"], "summary": summary, "steps": steps}

    max_steps = config.settings.agent.recursion_limit
    # RAG + 长期记忆注入（失败不影响执行）
    context = ""
    try:
        context = await build_context(task.goal + " " + json.dumps(task.params, ensure_ascii=False))
    except Exception:
        pass
    # 对话历史（排除当前轮用户消息，供多轮任务上下文）
    prior = [m for m in session.summary(10) if m.get("role") in ("user", "assistant")][:-1]
    context_lines = []
    if context:
        context_lines.append(f"以下是与任务相关的已知信息：\n{context}")
    if prior:
        lines = "\n".join(
            f"{'用户' if m['role'] == 'user' else '助手'}: {m['content']}"
            for m in prior if isinstance(m.get("content"), str)
        )
        context_lines.append(f"以下是最近对话：\n{lines}")
    base = f"{_SYSTEM}\n\n{UNTRUSTED_DATA_NOTE}"
    sys_prompt = f"{base}\n\n" + "\n\n".join(context_lines) if context_lines else base
    history = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": f"任务目标：{task.goal}\n参数：{json.dumps(task.params, ensure_ascii=False)}"},
    ]
    steps = []
    for step in range(max_steps):
        if cancel.is_cancelled:
            return {"status": "stopped", "summary": "已停止", "steps": steps}
        try:
            cancel.throw_if_cancelled()
            assistant_message = None
            async for evt in get_llm_client().retry_stream_chat(history, tools=TOOLS.schemas()):
                if evt["type"] == "done":
                    assistant_message = evt["message"]
                elif events is not None:
                    # 经 from_llm_event 统一口径转发：content_delta / reasoning_delta / usage
                    # （reasoning_delta 此前被静默丢弃 —— 思考流断链的修复点）
                    # Forward through from_llm_event (single convention): content_delta /
                    # reasoning_delta / usage. reasoning_delta used to be silently dropped —
                    # the fix for the broken thinking stream.
                    forwarded = from_llm_event(evt)
                    if forwarded is not None:
                        await events.put(forwarded)
            if assistant_message is None:
                return {"status": "failed", "summary": "LLM 返回空消息", "steps": steps}

            history.append(assistant_message)
            tool_calls = assistant_message.get("tool_calls") or []
            if not tool_calls:
                summary = assistant_message.get("content") or "完成"
                session.append("assistant", summary)
                return {"status": "done", "summary": summary, "steps": steps}

            async def run_one_tc(tc: dict, step: int) -> tuple[dict, dict] | None:
                """执行单个工具调用，返回 (steps条目, tool消息)；取消返回 None。

                Execute a single tool call, returning (steps entry, tool message);
                return None when cancelled.
                """
                cancel.throw_if_cancelled()
                name = tc["function"]["name"]
                call_id = tc.get("id", "")
                raw = tc["function"].get("arguments") or "{}"
                try:
                    args = json.loads(raw) if isinstance(raw, str) else raw
                except json.JSONDecodeError:
                    args = {}
                if events is not None:
                    await events.put(ToolStartEvent(name=name, args=args, call_id=call_id).emit())
                # 高风险工具先确认（基于工具实际风险，而非任务声明的 risk）
                ok = await confirm_tool(session, name, args)
                result = (await TOOLS.acall(name, args, cancel=cancel, session=session)
                          if ok else f"Error: 操作者拒绝调用 {name}")
                status = "error" if result.startswith("Error") else "ok"
                if events is not None:
                    await events.put(ToolEndEvent(
                        name=name, status=status, output=result[:PREVIEW_LEN],
                        call_id=call_id, truncated=len(result) > PREVIEW_LEN,
                        output_len=len(result),
                    ).emit())
                return (
                    {"step": step, "tool": name, "args": args, "status": status, "result": result[:PREVIEW_LEN]},
                    {"role": "tool", "tool_call_id": call_id, "content": result},
                )

            # 免确认的工具并发执行；需确认的逐个串行（确认本身必须串行问）。
            # 分流依据是「是否需要确认」而非工具风险 —— 策略 allow 的写操作同样免确认。
            # Tools needing no confirmation run concurrently; those needing it run one at a
            # time (the confirmation itself must be asked serially). The split is by
            # "needs confirmation", not by tool risk: a policy-allowed write is equally
            # prompt-free.
            auto_idx = [i for i, tc in enumerate(tool_calls)
                        if decide(tc["function"]["name"]).action == "allow"]
            auto_set = set(auto_idx)
            ask_idx = [i for i in range(len(tool_calls)) if i not in auto_set]
            results: dict[int, tuple[dict, dict]] = {}
            if auto_idx:
                outs = await asyncio.gather(*(run_one_tc(tool_calls[i], step) for i in auto_idx))
                for i, o in zip(auto_idx, outs):
                    if o is not None:
                        results[i] = o
            for i in ask_idx:
                o = await run_one_tc(tool_calls[i], step)
                if o is not None:
                    results[i] = o
            # 按原 tool_calls 顺序落 steps/history，保持回喂顺序稳定
            for i in sorted(results):
                step_entry, tool_msg = results[i]
                steps.append(step_entry)
                history.append(tool_msg)
                # 工具以 tool 块入会话（不再产生独立 "tool" 消息行）：
                # output 入库截 HISTORY_LEN、预览/完整长度随块记录；content 投影
                # 里的 "name: output[:200]" 文本行承担旧读路径兼容。
                # Tools enter the session as tool blocks (no standalone "tool" message
                # rows): output is stored up to HISTORY_LEN with preview/full lengths
                # recorded; the "name: output[:200]" line in the content projection
                # serves legacy read paths.
                full_out = tool_msg["content"]
                session.append_block("assistant", make_block("tool", {
                    "call_id": tool_msg.get("tool_call_id", ""),
                    "name": step_entry["tool"],
                    "args": step_entry.get("args", {}),
                    "status": step_entry["status"],
                    "output": full_out[:HISTORY_LEN],
                    "output_preview": full_out[:PREVIEW_LEN],
                    "truncated": len(full_out) > PREVIEW_LEN,
                    "full_len": len(full_out),
                }))
        except asyncio.CancelledError:
            return {"status": "stopped", "summary": "已停止", "steps": steps}
        except Exception as e:
            logger.error("executor 执行异常: {}", e)
            return {"status": "failed", "summary": f"执行失败: {e}", "steps": steps}
    return {"status": "failed", "summary": f"超出执行步数上限（{max_steps}）", "steps": steps}
