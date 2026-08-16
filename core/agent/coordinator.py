# -*- coding: utf-8 -*-
"""多智能体协调者 — 拆解任务 → 子代理执行（独立并发）→ critic 审查 → 合并"""
import asyncio
import json
from types import SimpleNamespace
from typing import Any

from core.agent.base import run_subagent
from core.llm.client import get_llm_client
from core.logger import logger
from core.orchestrator.control import CancellationToken
from core.orchestrator.session import Session
from core.orchestrator.task import Task

MAX_CONCURRENT = 4

_ROLE_PROMPTS = {
    "planner": "你是规划子代理：把目标拆成有序、可执行的步骤，给出清晰计划。",
    "doer": "你是执行子代理：用工具完成子任务，直接给出结果。",
    "searcher": "你是检索子代理：搜索/查询信息（网络/文件/记忆），给出信息摘要。",
    "critic": "你是批评子代理：审查执行结果是否达成目标、有无遗漏或错误，指出问题并给出改进建议。",
}

_DECOMPOSE_TOOL = {
    "type": "function",
    "function": {
        "name": "decompose",
        "description": "把任务拆成子任务",
        "parameters": {
            "type": "object",
            "properties": {
                "subtasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "goal": {"type": "string"},
                            "agent_type": {"type": "string", "enum": ["planner", "doer", "searcher"]},
                            "independent": {"type": "boolean", "description": "是否可与其他子任务并行"},
                        },
                        "required": ["goal", "agent_type", "independent"],
                    },
                },
            },
            "required": ["subtasks"],
        },
    },
}


async def _decompose(task: Task) -> list[dict]:
    messages = [
        {"role": "system", "content": "把任务拆成子任务，用 decompose 工具返回。每项含 goal、agent_type（planner/doer/searcher）、independent（是否可并行）。"},
        {"role": "user", "content": f"任务：{task.goal}，参数：{json.dumps(task.params, ensure_ascii=False)}"},
    ]
    try:
        async for evt in get_llm_client().retry_stream_chat(messages, tools=[_DECOMPOSE_TOOL]):
            if evt["type"] == "done":
                msg = evt["message"]
                tc = (msg.get("tool_calls") or [{}])[0]
                raw = tc.get("function", {}).get("arguments") or "{}"
                data = json.loads(raw) if isinstance(raw, str) else raw
                return [{
                    "goal": str(s.get("goal", "")),
                    "agent_type": s.get("agent_type", "doer"),
                    "independent": bool(s.get("independent", False)),
                } for s in data.get("subtasks") or []]
    except Exception as e:
        logger.warning("decompose 失败，退化为单子任务: {}", e)
    return [{"goal": task.goal, "agent_type": "doer", "independent": False}]


async def run_coordinator(task: Task, session: Session, cancel: CancellationToken) -> dict:
    """拆解→执行→critic→合并。返回 {status, summary, subtasks}。"""
    if cancel.is_cancelled:
        return {"status": "stopped", "summary": "已停止", "subtasks": []}
    subtasks = await _decompose(task)
    if cancel.is_cancelled:
        return {"status": "stopped", "summary": "已停止", "subtasks": []}
    await session.notify(f"已拆分 {len(subtasks)} 个子任务")

    executed: list[dict] = []

    async def run_one(s: dict) -> None:
        await session.notify(f"子代理 {s['agent_type']} 开始：{s['goal'][:50]}")
        r = await run_subagent(
            _ROLE_PROMPTS.get(s["agent_type"], _ROLE_PROMPTS["doer"]),
            s["goal"], context=task.goal, cancel=cancel,
        )
        executed.append({
            "goal": s["goal"], "agent_type": s["agent_type"],
            "status": r.status, "output": r.output[:300], "tools": r.used_tools,
        })
        await session.notify(f"子代理 {s['agent_type']} 完成（{r.status}）")

    indep = [s for s in subtasks if s["independent"]]
    dep = [s for s in subtasks if not s["independent"]]

    if indep:
        sem = asyncio.Semaphore(MAX_CONCURRENT)

        async def limited(s: dict) -> None:
            async with sem:
                await run_one(s)

        await asyncio.gather(*(limited(s) for s in indep))
    for s in dep:
        await run_one(s)

    if cancel.is_cancelled:
        return {"status": "stopped", "summary": "已停止", "subtasks": executed}

    # critic 审查
    merged = "\n".join(f"- {x['goal']}: {x['output']}" for x in executed)
    critique = ""
    await session.notify("批评子代理审查中…")
    critic = await run_subagent(
        _ROLE_PROMPTS["critic"],
        f"审查以下子任务结果是否达成主任务「{task.goal}」，指出问题：\n{merged}",
        cancel=cancel,
    )
    critique = critic.output[:500]

    failed = any(x["status"] in ("failed", "stopped") for x in executed)
    return {
        "status": "failed" if failed else "done",
        "summary": merged + (f"\n\n[审查] {critique}" if critique else ""),
        "subtasks": executed,
    }
