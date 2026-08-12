# -*- coding: utf-8 -*-
"""执行循环 — plan → act(调工具) → observe(回喂) → reflect，可取消、可收敛

高风险工具（risk != read）在调用前经 confirm_if_needed 确认。
取消（CancelledError）统一收敛为 status=stopped 返回，调用方无需捕获。
"""
import asyncio
import json

from core.config import cfg
from core.llm.client import get_llm_client
from core.logger import logger
from core.orchestrator.confirm import confirm_if_needed
from core.orchestrator.control import CancellationToken
from core.orchestrator.session import Session
from core.orchestrator.task import Task
from core.tools import TOOLS

_SYSTEM = ("你是执行助手。用工具完成任务。每步：需要时就调用工具；拿到结果后判断是否已达成目标；"
           "达成目标就给出最终结论（不要再调工具）。")


async def execute_task(task: Task, session: Session, cancel: CancellationToken) -> dict:
    """ReAct 执行循环，返回 {status: done|failed|stopped, summary, steps:[...]}。"""
    if cancel.is_cancelled:
        return {"status": "stopped", "summary": "已停止", "steps": []}
    max_steps = cfg("agent.recursion_limit", 12)
    history = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": f"任务目标：{task.goal}\n参数：{json.dumps(task.params, ensure_ascii=False)}"},
    ]
    steps: list[dict] = []
    for step in range(max_steps):
        if cancel.is_cancelled:
            return {"status": "stopped", "summary": "已停止", "steps": steps}
        try:
            cancel.throw_if_cancelled()
            assistant_message = None
            async for evt in get_llm_client().retry_stream_chat(history, tools=TOOLS.schemas()):
                if evt["type"] == "done":
                    assistant_message = evt["message"]
            if assistant_message is None:
                return {"status": "failed", "summary": "LLM 返回空消息", "steps": steps}

            history.append(assistant_message)
            tool_calls = assistant_message.get("tool_calls") or []
            if not tool_calls:
                return {"status": "done", "summary": assistant_message.get("content") or "完成", "steps": steps}

            for tc in tool_calls:
                cancel.throw_if_cancelled()
                name = tc["function"]["name"]
                raw = tc["function"].get("arguments") or "{}"
                try:
                    args = json.loads(raw) if isinstance(raw, str) else raw
                except json.JSONDecodeError:
                    args = {}
                # 高风险工具先确认
                if TOOLS.risk(name) != "read":
                    plan = f"调用工具 {name}，参数 {json.dumps(args, ensure_ascii=False)}"
                    ok = await confirm_if_needed(task, plan, session)
                    result = await TOOLS.acall(name, args) if ok else f"Error: 操作者拒绝调用 {name}"
                else:
                    result = await TOOLS.acall(name, args)
                status = "error" if result.startswith("Error") else "ok"
                steps.append({"step": step, "tool": name, "args": args, "status": status, "result": result[:500]})
                history.append({"role": "tool", "tool_call_id": tc.get("id", ""), "content": result})
                session.append("tool", f"{name}: {result[:200]}")
        except asyncio.CancelledError:
            return {"status": "stopped", "summary": "已停止", "steps": steps}
        except Exception as e:
            logger.error("executor 执行异常: {}", e)
            return {"status": "failed", "summary": f"执行失败: {e}", "steps": steps}
    return {"status": "failed", "summary": f"超出执行步数上限（{max_steps}）", "steps": steps}
