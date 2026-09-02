# -*- coding: utf-8 -*-
"""schedule 域 API — 定时任务（cron）注册/列表/取消。

Schedule domain API — cron job registration / listing / cancellation.
"""
import json
from dataclasses import asdict

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core.api.schemas import ApiResponse, ScheduleAddResponse, SchedulesResponse

router = APIRouter()


@router.get("/schedules", response_model=SchedulesResponse)
async def schedules_list():
    """列出全部已注册的定时任务。

    List all registered scheduled jobs.
    """
    from core.scheduler.scheduler import get_scheduler
    return {"ok": True, "schedules": [asdict(s) for s in get_scheduler().all()]}


@router.post("/schedules", response_model=ScheduleAddResponse)
async def schedules_add(request: Request):
    """注册一个定时任务：body {cron, prompt}，cron 与 prompt 必填。

    Register a scheduled job: body {cron, prompt}; cron and prompt are required.
    """
    from core.scheduler.scheduler import get_scheduler
    body = await request.body()
    try:
        params = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        return JSONResponse({"ok": False, "error": "无效 JSON"}, status_code=400)
    cron = (params.get("cron") or "").strip()
    prompt = (params.get("prompt") or "").strip()
    if not cron or not prompt:
        return JSONResponse({"ok": False, "error": "cron 与 prompt 必填"}, status_code=400)
    sc = get_scheduler().add(cron, prompt)
    return {"ok": True, "schedule": asdict(sc)}


@router.delete("/schedules/{sid}", response_model=ApiResponse)
async def schedules_delete(sid: str):
    """按 ID 取消一个定时任务。

    Cancel a scheduled job by its ID.
    """
    from core.scheduler.scheduler import get_scheduler
    get_scheduler().remove(sid)
    return {"ok": True}
