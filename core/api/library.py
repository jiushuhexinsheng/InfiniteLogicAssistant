# -*- coding: utf-8 -*-
"""任务库 API（已下线，docs/designs/10 6.1）。

`TaskStore` 没有任何运行时写入方（`record()` / `find_similar()` 无调用），任务库永远
是空的，产品上不再暴露。端点保留一个版本，避免旧前端直接报错：
列表返回空数组；详情/删除返回 410 Gone。

Task library API (retired, docs/designs/10 6.1). `TaskStore` has no runtime writer
(`record()` / `find_similar()` are never called), so the library can only ever be
empty and is no longer exposed in the product. The endpoints stay for one release so
old frontends do not break: the list returns an empty array; detail/delete return
410 Gone.
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from core.api.schemas import ApiResponse, LibraryDetailResponse, LibraryListResponse

router = APIRouter()

_GONE = "任务库已下线（无运行时写入方）。Task library is retired."


@router.get("/library", response_model=LibraryListResponse)
async def library_list():
    """列出已存档任务 —— 库已下线，恒为空。

    List archived tasks — the library is retired, so this is always empty.
    """
    return {"ok": True, "tasks": []}


@router.get("/library/{task_id}", response_model=LibraryDetailResponse)
async def library_detail(task_id: int):
    """取单条任务详情 —— 已下线。Fetch one archived task — retired."""
    return JSONResponse({"ok": False, "error": _GONE}, status_code=410)


@router.delete("/library/{task_id}", response_model=ApiResponse)
async def library_delete(task_id: int):
    """删除一条任务存档 —— 已下线。Delete one archived task — retired."""
    return JSONResponse({"ok": False, "error": _GONE}, status_code=410)
