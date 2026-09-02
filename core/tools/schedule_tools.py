# -*- coding: utf-8 -*-
"""定时任务工具 — 注册/列出/取消（语音可调）

Scheduled-task tools — register/list/cancel (voice-invocable)
"""
from core.scheduler.scheduler import get_scheduler
from core.tools.base import tool


@tool("注册定时任务（cron 5 段：分 时 日 月 周，如 '0 9 * * *' 每天9点）", risk="write")
async def register_schedule(cron: str, prompt: str) -> str:
    """注册定时任务（cron 5 段：分 时 日 月 周）。Register a scheduled task (5-field cron: minute hour day month weekday).

    Args:
        cron: cron 表达式。Cron expression.
        prompt: 任务内容。Task prompt.

    Returns:
        注册成功提示（含任务 id）。Success message including the task id.
    """
    sc = get_scheduler().add(cron, prompt)
    return f"已注册定时任务 {sc.id}：cron={cron}，内容={prompt}"


@tool("列出定时任务", risk="read")
async def list_schedules() -> str:
    """列出所有定时任务。List all scheduled tasks.

    Returns:
        任务列表字符串；无任务时返回 "暂无定时任务"。Task list; "暂无定时任务" when empty.
    """
    scs = get_scheduler().all()
    if not scs:
        return "暂无定时任务"
    return "\n".join(f"- {sc.id} [{sc.cron}] {sc.prompt}" for sc in scs)


@tool("取消定时任务", risk="write")
async def remove_schedule(id: str) -> str:
    """取消指定定时任务。Cancel a scheduled task by id.

    Args:
        id: 任务 id。Task id.

    Returns:
        取消成功提示。Success message.
    """
    get_scheduler().remove(id)
    return f"已取消定时任务 {id}"
