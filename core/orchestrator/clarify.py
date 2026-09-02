# -*- coding: utf-8 -*-
"""澄清循环 — 把任务缺失信息转成问题问操作者，回答后回填，循环到信息足够。

Clarification loop — turns the task's missing information into questions for the
operator, refills the answers, and loops until enough information is gathered.
"""
from core.logger import logger
from core.orchestrator.intent import IntentResult
from core.orchestrator.session import Session
from core.orchestrator.task import Task, form_task

MAX_CLARIFY_ROUNDS = 3


async def run_clarify(session: Session, task: Task) -> dict:
    """逐条把 task.missing 问给操作者，用回答重新形成任务，直到 missing 为空或轮次/重复上限。

    每轮把全部已答问题并入上下文重形成任务；已确认参数保留合并、已问问题不再追问，
    避免 LLM 重新生成时丢掉前几轮参数或重复提问。

    Asks the operator each item in task.missing one by one, re-forming the task
    with the answers until missing is empty or the round/repetition limit is hit.
    Each round merges all answered questions into the context before re-forming
    the task; already confirmed params are kept and merged, and already asked
    questions are not asked again, so the LLM neither drops earlier params nor
    repeats questions.
    """
    asked: set[str] = set()
    answered: dict[str, str] = {}
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
        answered[q] = ans
        # 全部已答作为结构化 confirmed 传入重新形成任务（goal 保持干净）
        new_task = await form_task(IntentResult(type="task", summary=task.goal), confirmed=answered)
        task.goal = new_task.goal or task.goal
        # 保留先前已确认参数，新结果覆盖同名键
        task.params = {**task.params, **new_task.params}
        # 过滤已问过的问题，避免 LLM 重问
        task.missing = [m for m in new_task.missing if m not in asked]
    return dict(task.params)
