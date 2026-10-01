# -*- coding: utf-8 -*-
"""定时任务端点响应。Scheduled-task endpoint responses."""
from pydantic import BaseModel

from .base import ApiResponse

# ─────────────────────────── schedules ───────────────────────────

class ScheduleItem(BaseModel):
    """单条定时任务。

    A single scheduled task entry.
    """
    id: str
    cron: str
    prompt: str
    enabled: bool = True

class SchedulesResponse(ApiResponse):
    """定时任务列表端点响应。

    ``/api/schedules`` list response.
    """
    schedules: list[ScheduleItem] = []

class ScheduleAddResponse(ApiResponse):
    """添加定时任务端点响应。

    ``/api/schedules/add`` response.
    """
    schedule: ScheduleItem | None = None

