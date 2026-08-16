# -*- coding: utf-8 -*-
"""schedule 域 API — 定时任务（cron）注册/列表/取消"""
import json
from dataclasses import asdict

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/schedules")
async def schedules_list():
    from core.scheduler.scheduler import get_scheduler
    return {"ok": True, "schedules": [asdict(s) for s in get_scheduler().all()]}


@router.post("/schedules")
async def schedules_add(request: Request):
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


@router.delete("/schedules/{sid}")
async def schedules_delete(sid: str):
    from core.scheduler.scheduler import get_scheduler
    get_scheduler().remove(sid)
    return {"ok": True}
