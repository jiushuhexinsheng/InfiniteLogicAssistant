# -*- coding: utf-8 -*-
"""执行循环 — plan → act(调工具) → observe(回喂) → reflect，可取消、可收敛

高风险工具（risk != read）在调用前经 confirm_if_needed 确认。
取消（CancelledError）统一收敛为 status=stopped 返回，调用方无需捕获。
"""
import asyncio
import json

from core.agent.coordinator import run_coordinator
from core.config import cfg
from core.llm.client import get_llm_client
from core.logger import logger
from core.memory.context import build_context
from core.orchestrator.confirm import confirm_if_needed
from core.orchestrator.control import CancellationToken
from core.orchestrator.session import Session
from core.orchestrator.task import Task
from core.tools import TOOLS

_SYSTEM = ("你是执行助手。用工具完成任务。每步：需要时就调用工具；拿到结果后判断是否已达成目标；"
           "达成目标就给出最终结论（不要再调工具）。"
           "若用户要求'记住/以后/偏好/我喜欢'等记忆类陈述，调用 memory_put 写入长期记忆。")


def should_use_multi_agent(task: Task) -> bool:
    """复杂任务（启用多智能体且多参数/长目标）转协调者。"""
    return cfg("agent.multi_agent", False) and (len(task.params) >= 2 or len(task.goal) > 30)


async def execute_task(task: Task, session: Session, cancel: CancellationToken,
                       events: asyncio.Queue | None = None) -> dict:
    """执行任务：复杂任务转多智能体协调者；简单任务走 ReAct。

    events 非空时流式发射 tool_start/tool_end/usage/content_delta（SSE 实时呈现）。
    返回 {status: done|failed|stopped, summary, steps:[...]}。
    """
    if cancel.is_cancelled:
        return {"status": "stopped", "summary": "已停止", "steps": []}

    # 复杂任务 → 多智能体
    if should_use_multi_agent(task):
        cr = await run_coordinator(task, session, cancel)
        steps = [
            {"step": i, "tool": f"agent:{x['agent_type']}", "status": x["status"], "result": x["output"]}
            for i, x in enumerate(cr["subtasks"])
        ]
        return {"status": cr["status"], "summary": cr["summary"], "steps": steps}

    max_steps = cfg("agent.recursion_limit", 12)
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
    sys_prompt = f"{_SYSTEM}\n\n" + "\n\n".join(context_lines) if context_lines else _SYSTEM
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
                elif events is not None and evt["type"] in ("content_delta", "usage"):
                    await events.put(evt)
            if assistant_message is None:
                return {"status": "failed", "summary": "LLM 返回空消息", "steps": steps}

            history.append(assistant_message)
            tool_calls = assistant_message.get("tool_calls") or []
            if not tool_calls:
                return {"status": "done", "summary": assistant_message.get("content") or "完成", "steps": steps}

            async def run_one_tc(tc: dict, step: int) -> tuple[dict, dict] | None:
                """执行单个工具调用，返回 (steps条目, tool消息)；取消返回 None。"""
                cancel.throw_if_cancelled()
                name = tc["function"]["name"]
                raw = tc["function"].get("arguments") or "{}"
                try:
                    args = json.loads(raw) if isinstance(raw, str) else raw
                except json.JSONDecodeError:
                    args = {}
                if events is not None:
                    await events.put({"type": "tool_start", "name": name, "args": args})
                # 高风险工具先确认
                if TOOLS.risk(name) != "read":
                    plan = f"调用工具 {name}，参数 {json.dumps(args, ensure_ascii=False)}"
                    ok = await confirm_if_needed(task, plan, session)
                    result = await TOOLS.acall(name, args) if ok else f"Error: 操作者拒绝调用 {name}"
                else:
                    result = await TOOLS.acall(name, args)
                status = "error" if result.startswith("Error") else "ok"
                if events is not None:
                    await events.put({"type": "tool_end", "name": name, "status": status, "output": result[:500]})
                return (
                    {"step": step, "tool": name, "args": args, "status": status, "result": result[:500]},
                    {"role": "tool", "tool_call_id": tc.get("id", ""), "content": result},
                )

            # read 级工具并发执行（相互独立）；write/exec 串行（需逐个人类确认）
            read_idx = [i for i, tc in enumerate(tool_calls) if TOOLS.risk(tc["function"]["name"]) == "read"]
            write_idx = [i for i, tc in enumerate(tool_calls) if TOOLS.risk(tc["function"]["name"]) != "read"]
            results: dict[int, tuple[dict, dict]] = {}
            if read_idx:
                outs = await asyncio.gather(*(run_one_tc(tool_calls[i], step) for i in read_idx))
                for i, o in zip(read_idx, outs):
                    if o is not None:
                        results[i] = o
            for i in write_idx:
                o = await run_one_tc(tool_calls[i], step)
                if o is not None:
                    results[i] = o
            # 按原 tool_calls 顺序落 steps/history，保持回喂顺序稳定
            for i in sorted(results):
                step_entry, tool_msg = results[i]
                steps.append(step_entry)
                history.append(tool_msg)
                session.append("tool", f"{step_entry['tool']}: {step_entry['result'][:200]}")
        except asyncio.CancelledError:
            return {"status": "stopped", "summary": "已停止", "steps": steps}
        except Exception as e:
            logger.error("executor 执行异常: {}", e)
            return {"status": "failed", "summary": f"执行失败: {e}", "steps": steps}
    return {"status": "failed", "summary": f"超出执行步数上限（{max_steps}）", "steps": steps}
