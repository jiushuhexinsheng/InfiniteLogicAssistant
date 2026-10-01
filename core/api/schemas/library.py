# -*- coding: utf-8 -*-
"""任务库端点响应。Task-library endpoint responses."""
from typing import Any

from pydantic import BaseModel

from .base import ApiResponse

class TaskLibraryItem(BaseModel):
    """任务库条目（一次成功任务的存档）。

    One archived successful task.
    """
    id: int
    goal: str
    params: dict[str, Any] = {}
    steps: list[Any] = []
    status: str = ""
    created: str = ""
    session_id: str = ""

class LibraryListResponse(ApiResponse):
    """任务库列表响应。

    The task-library list response.
    """
    tasks: list[TaskLibraryItem] = []

class LibraryDetailResponse(ApiResponse):
    """任务库详情响应。

    The task-library detail response.
    """
    task: TaskLibraryItem
