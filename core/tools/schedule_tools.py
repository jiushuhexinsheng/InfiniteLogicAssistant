# -*- coding: utf-8 -*-
"""定时任务工具 — 注册/列出/取消（语音可调）"""
from core.scheduler.scheduler import get_scheduler
from core.tools.base import tool


@tool("注册定时任务（cron 5 段：分 时 日 月 周，如 '0 9 * * *' 每天9点）", risk="write")
async def register_schedule(cron: str, prompt: str) -> str:
    sc = get_scheduler().add(cron, prompt)
    return f"已注册定时任务 {sc.id}：cron={cron}，内容={prompt}"


@tool("列出定时任务", risk="read")
async def list_schedules() -> str:
    scs = get_scheduler().list()
    if not scs:
        return "暂无定时任务"
    return "\n".join(f"- {sc.id} [{sc.cron}] {sc.prompt}" for sc in scs)


@tool("取消定时任务", risk="write")
async def remove_schedule(id: str) -> str:
    get_scheduler().remove(id)
    return f"已取消定时任务 {id}"
