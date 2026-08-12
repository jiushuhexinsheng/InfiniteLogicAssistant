# -*- coding: utf-8 -*-
"""澄清循环 — 把任务缺失信息转成问题问操作者，回答后回填，循环到信息足够"""
from core.logger import logger
from core.orchestrator.intent import IntentResult
from core.orchestrator.session import Session
from core.orchestrator.task import Task, form_task

MAX_CLARIFY_ROUNDS = 3


async def run_clarify(session: Session, task: Task) -> dict:
    """逐条把 task.missing 问给操作者，用回答重新形成任务，直到 missing 为空或轮次/重复上限。"""
    asked: set[str] = set()
    for _ in range(MAX_CLARIFY_ROUNDS):
        if not task.missing:
            break
        q = task.missing[0]
        if q in asked:
            logger.warning("澄清重复问题，停止追问: {}", q)
            break
        asked.add(q)
        ans = (await session.ask(q)).strip()
        if not ans:
            break
        # 把回答并入上下文重新形成任务，得到更新后的 params/missing
        new_task = await form_task(IntentResult(type="task", summary=f"{task.goal}（{q}→{ans}）"))
        task.goal = new_task.goal
        task.params = new_task.params
        task.missing = new_task.missing
    return dict(task.params)
