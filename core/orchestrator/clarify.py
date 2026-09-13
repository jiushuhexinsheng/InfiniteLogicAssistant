# -*- coding: utf-8 -*-
"""澄清循环 — 把任务缺失信息转成问题问操作者，回答后回填，循环到信息足够。

Clarification loop — turns the task's missing information into questions for the
operator, refills the answers, and loops until enough information is gathered.
"""
from core.logger import logger
from core.orchestrator.intent import IntentResult
from core.orchestrator.session import Answer, Session
from core.orchestrator.task import MissingItem, Task, form_task

MAX_CLARIFY_ROUNDS = 3


async def run_clarify(session: Session, task: Task) -> dict:
    """逐条把 task.missing 问给操作者，用回答重新形成任务，直到 missing 为空或轮次/重复上限。

    每条缺失信息自带作答方式（MissingItem.type/options）：text 走自由文本，
    choice/composite 走结构化选择。选择类回答回填 **option 的 label**（人类可读，
    便于模型理解），value 在选项中找不到时回退为原始值。

    Asks the operator each item in task.missing one by one, re-forming the task with the
    answers until missing is empty or the round/repetition limit is hit. Each missing item
    carries how it should be answered (MissingItem.type/options): text uses free input
    while choice/composite use a structured choice. A choice answer backfills the option's
    **label** (human-readable, for the model to understand), falling back to the raw value
    when it is not among the options.
    """
    asked: set[str] = set()
    answered: dict[str, str] = {}
    for _ in range(MAX_CLARIFY_ROUNDS):
        if not task.missing:
            break
        item = task.missing[0]
        if item.question in asked:
            logger.warning("澄清重复问题，停止追问: {}", item.question)
            break
        asked.add(item.question)
        answer = await session.ask(item.question, kind=item.type, options=item.options)
        text = _answer_text(answer, item)
        if not text:
            break
        answered[item.question] = text
        # 全部已答作为结构化 confirmed 传入重新形成任务（goal 保持干净）
        new_task = await form_task(IntentResult(type="task", summary=task.goal), confirmed=answered)
        task.goal = new_task.goal or task.goal
        # 保留先前已确认参数，新结果覆盖同名键
        task.params = {**task.params, **new_task.params}
        # 过滤已问过的问题（按 question 文本），避免 LLM 重问
        task.missing = [m for m in new_task.missing if m.question not in asked]
    return dict(task.params)


def _answer_text(answer: Answer, item: MissingItem) -> str:
    """把一条回答转成回填给 LLM 的文本。

    选择类取被选 option 的 label；找不到时回退原始 value。文本类取 text。

    Convert an answer into the text backfilled to the LLM. A choice answer takes the
    selected option's label, falling back to the raw value when not found; a text answer
    takes its text.

    Args:
        answer: 操作者回答。The operator's answer.
        item: 对应的缺失信息。The corresponding missing item.

    Returns:
        供回填的文本，可能为空串。The text to backfill, possibly empty.
    """
    if answer.choice is not None:
        for opt in item.options:
            if opt.get("value") == answer.choice:
                return str(opt.get("label") or answer.choice)
        return answer.choice
    return answer.text.strip()
