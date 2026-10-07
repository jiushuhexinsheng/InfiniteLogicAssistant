# -*- coding: utf-8 -*-
"""多智能体协调者 — 拆解任务 → 子代理执行（独立并发）→ critic 审查 → 合并

Multi-agent coordinator — decompose task → sub-agent execution (independent
concurrency) → critic review → merge results.
"""
import asyncio
import json

from core import config
from core.agent.base import run_subagent
from core.llm.client import get_llm_client
from core.logger import logger
from core.memory.context import build_context
from core.orchestrator.confirm import ConfirmResult, confirm_tool
from core.orchestrator.control import CancellationToken
from core.orchestrator.session import Session
from core.orchestrator.task import Task
from core.prompts import DECOMPOSE_SYSTEM, ROLE_PROMPTS as _ROLE_PROMPTS

# 最大并发子代理数 / Max concurrent sub-agents
MAX_CONCURRENT = 4

_DECOMPOSE_TOOL = {
    "type": "function",
    "function": {
        "name": "decompose",
        "description": "把任务拆成子任务（最多 6 个；每项写清目标/输出格式/边界）",
        "parameters": {
            "type": "object",
            "properties": {
                "subtasks": {
                    "type": "array",
                    # 数量上限（docs/designs/08 批3）：无界拆解 = token 复利失控。
                    # Cap (docs/designs/08 batch 3): unbounded decomposition compounds token cost.
                    "maxItems": 6,
                    "items": {
                        "type": "object",
                        "properties": {
                            "goal": {"type": "string", "description": "子任务目标（一句话）"},
                            "agent_type": {"type": "string", "enum": ["planner", "doer", "searcher"]},
                            "independent": {"type": "boolean", "description": "是否可与其他子任务并行"},
                            # 委派四要素之二三（docs/designs/08 批3）：输出格式与边界。
                            # Elements 2 & 3 of the delegation quartet (docs/designs/08 batch 3).
                            "output_format": {"type": "string", "description": "期望输出形态（如：步骤清单/一段结论/带来源的列表）"},
                            "boundary": {"type": "string", "description": "边界：只做什么、明确不做什么"},
                        },
                        "required": ["goal", "agent_type", "independent"],
                    },
                },
            },
            "required": ["subtasks"],
        },
    },
}


async def _decompose(task: Task, ctx: str = "") -> list[dict]:
    """调用 LLM 把任务拆成多个子任务（含 goal / agent_type / independent）。

    失败时退化为单个 doer 子任务。

    Call the LLM to decompose the task into sub-tasks (each with ``goal``,
    ``agent_type``, ``independent``).

    Falls back to a single ``doer`` sub-task on failure.
    """
    user = f"任务：{task.goal}，参数：{json.dumps(task.params, ensure_ascii=False)}"
    if ctx:
        user += f"\n已知信息：{ctx}"
    messages = [
        {"role": "system", "content": DECOMPOSE_SYSTEM},
        {"role": "user", "content": user},
    ]
    try:
        async for evt in get_llm_client().retry_stream_chat(
            messages, tools=[_DECOMPOSE_TOOL], temperature=config.settings.agent.structured_temperature,
        ):
            if evt["type"] == "done":
                msg = evt["message"]
                tc = (msg.get("tool_calls") or [{}])[0]
                raw = tc.get("function", {}).get("arguments") or "{}"
                data = json.loads(raw) if isinstance(raw, str) else raw
                return [{
                    "goal": str(s.get("goal", "")),
                    "agent_type": s.get("agent_type", "doer"),
                    "independent": bool(s.get("independent", False)),
                    "output_format": str(s.get("output_format") or ""),
                    "boundary": str(s.get("boundary") or ""),
                } for s in data.get("subtasks") or []]
    except Exception as e:
        logger.warning("decompose 失败，退化为单子任务: {}", e)
    return [{"goal": task.goal, "agent_type": "doer", "independent": False}]


async def run_coordinator(task: Task, session: Session, cancel: CancellationToken,
                          events: asyncio.Queue | None = None) -> dict:
    """拆解→执行→critic→合并。返回 {status, summary, subtasks}。

    Decompose → execute → critic review → merge.
    Return ``{status, summary, subtasks}``.
    """
    if cancel.is_cancelled:
        return {"status": "stopped", "summary": "已停止", "subtasks": []}

    async def _confirm(name: str, args: dict) -> ConfirmResult:
        """子代理工具确认：read 放行，write/exec 问操作者（无人值守自动拒绝）。

        返回 ConfirmResult（含拒绝理由），透传给子代理回喂 LLM。

        Sub-agent tool confirmation: ``read`` tools pass automatically;
        ``write`` / ``exec`` ask the operator (auto-reject when unattended).
        Returns the ConfirmResult (with the refusal rationale) so the sub-agent
        can feed it back to the LLM.
        """
        return await confirm_tool(session, name, args)

    # RAG + 长期记忆注入（失败不影响执行；复杂任务不应缺失关键上下文）
    ctx = ""
    try:
        ctx = await build_context(task.goal + " " + json.dumps(task.params, ensure_ascii=False))
    except Exception:
        pass

    subtasks = await _decompose(task, ctx=ctx)
    if cancel.is_cancelled:
        return {"status": "stopped", "summary": "已停止", "subtasks": []}
    await session.notify(f"已拆分 {len(subtasks)} 个子任务")

    executed: list[dict] = []

    def _save_artifact(text: str, agent_type: str) -> str | None:
        """子代理完整产物落文件（docs/designs/08 批3）：critic 读全文、executed 只留预览。

        写失败返回 None（best-effort，不拖垮执行）。

        Persist a sub-agent's full output (docs/designs/08 batch 3): the critic reads
        the file, executed keeps only a preview. Returns None on failure (best-effort;
        execution never fails over it).
        """
        try:
            from uuid import uuid4
            d = config.ROOT_DIR / "data" / "agent_outputs" / session.id
            d.mkdir(parents=True, exist_ok=True)
            p = d / f"{agent_type}_{uuid4().hex[:8]}.md"
            p.write_text(text, encoding="utf-8")
            return str(p)
        except Exception as e:
            logger.warning("agent 产物落盘失败: {}", e)
            return None

    async def run_one(s: dict) -> None:
        """运行单个子任务并记录执行结果。

        Run a single sub-task and record its execution result.
        """
        # 委派要素拼进 goal（docs/designs/08 批3）：目标/输出格式/边界随任务一起下达。
        # Delegation elements fold into the goal (docs/designs/08 batch 3): target,
        # output format and boundary travel with the assignment.
        goal = s["goal"]
        if s.get("output_format"):
            goal += f"\n输出格式：{s['output_format']}"
        if s.get("boundary"):
            goal += f"\n边界：{s['boundary']}"
        await session.notify(f"子代理 {s['agent_type']} 开始：{s['goal'][:50]}")
        # 背景 = 主任务 goal + RAG/记忆上下文（沿用原 context=task.goal 语义，叠加注入）
        sub_context = f"{task.goal}\n\n{ctx}" if ctx else task.goal
        r = await run_subagent(
            _ROLE_PROMPTS.get(s["agent_type"], _ROLE_PROMPTS["doer"]),
            goal, context=sub_context, cancel=cancel, confirm=_confirm, events=events,
            agent=f"sub:{s['agent_type']}",
        )
        artifact = _save_artifact(r.output, s["agent_type"]) if r.output else None
        executed.append({
            "goal": s["goal"], "agent_type": s["agent_type"],
            "status": r.status, "output": r.output[:300], "tools": r.used_tools,
            "artifact": artifact,
        })
        await session.notify(f"子代理 {s['agent_type']} 完成（{r.status}）")

    indep = [s for s in subtasks if s["independent"]]
    dep = [s for s in subtasks if not s["independent"]]

    if indep:
        sem = asyncio.Semaphore(MAX_CONCURRENT)

        async def limited(s: dict) -> None:
            """信号量限流包装器，确保并发数不超过 MAX_CONCURRENT。

            Semaphore-bounded wrapper that ensures concurrency stays at or below
            ``MAX_CONCURRENT``.
            """
            async with sem:
                await run_one(s)

        await asyncio.gather(*(limited(s) for s in indep))
    for s in dep:
        await run_one(s)

    if cancel.is_cancelled:
        return {"status": "stopped", "summary": "已停止", "subtasks": executed}

    # critic 审查（docs/designs/08 批3）：预览 + 产物路径，critic 是子代理、可用
    # read_file 读全文 —— 不再基于 300 字残片做二手审查。
    # Critic review (docs/designs/08 batch 3): preview + artifact paths; the critic is
    # a sub-agent with read_file, so it reads the full text — no second-hand review
    # off a 300-char crumb.
    merged = "\n".join(
        f"- {x['goal']}: {x['output']}" + (f"\n  完整产物: {x['artifact']}" if x.get("artifact") else "")
        for x in executed
    )
    critique = ""
    await session.notify("批评子代理审查中…")
    critic_prompt = (f"审查以下子任务结果是否达成主任务「{task.goal}」，指出问题：\n{merged}\n"
                     "（有「完整产物」路径的条目可用 read_file 查看全文后再下结论。）")
    if ctx:
        critic_prompt += f"\n\n背景信息：\n{ctx}"
    critic = await run_subagent(
        _ROLE_PROMPTS["critic"], critic_prompt, cancel=cancel, confirm=_confirm, events=events,
        agent="sub:critic",
    )
    critique = critic.output[:500]

    failed = any(x["status"] in ("failed", "stopped") for x in executed)
    return {
        "status": "failed" if failed else "done",
        "summary": merged + (f"\n\n[审查] {critique}" if critique else ""),
        "subtasks": executed,
    }
