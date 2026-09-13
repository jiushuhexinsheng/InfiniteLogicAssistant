# -*- coding: utf-8 -*-
"""任务库 API — 成功任务存档的浏览与删除。

Task library API — browsing and deleting archived successful tasks.
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from core.api.schemas import ApiResponse, LibraryDetailResponse, LibraryListResponse
from core.tasks.store import TaskStore

router = APIRouter()

_store: TaskStore | None = None


def _get_store() -> TaskStore:
    """懒加载任务库单例（测试可替换本函数）。Lazily created singleton (tests replace this function).

    Returns:
        任务库存储。The task store.
    """
    global _store
    if _store is None:
        _store = TaskStore()
    return _store


@router.get("/library", response_model=LibraryListResponse)
async def library_list():
    """列出已存档的成功任务（按时间倒序）。

    List archived successful tasks, newest first.
    """
    return {"ok": True, "tasks": await _get_store().list_tasks()}


@router.get("/library/{task_id}", response_model=LibraryDetailResponse)
async def library_detail(task_id: int):
    """取单条任务详情。

    Fetch one archived task.
    """
    task = await _get_store().get_task(task_id)
    if task is None:
        return JSONResponse({"ok": False, "error": f"任务 {task_id} 不存在"}, status_code=404)
    return {"ok": True, "task": task}


@router.delete("/library/{task_id}", response_model=ApiResponse)
async def library_delete(task_id: int):
    """删除一条任务存档。

    Delete one archived task.
    """
    await _get_store().delete_task(task_id)
    return {"ok": True}
