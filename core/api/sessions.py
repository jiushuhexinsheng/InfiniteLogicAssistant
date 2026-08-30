# -*- coding: utf-8 -*-
"""sessions 域 API — 会话管理（新建 / 列表 / 重命名 / 删除）

会话 = 可续接对话线（history.db 的 conversations 记录，含 name）；对话续接走
POST /api/voice/utter 的 session_id 参数。
"""
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core.api.schemas import ApiResponse, SessionCreateResponse, SessionListResponse

router = APIRouter()


@router.post("/sessions", response_model=SessionCreateResponse)
async def sessions_create(request: Request):
    """新建会话（可选 body {"name"}；缺省名「新会话」），返回 {id, name, ...}。"""
    from core.session.history import get_history_store
    body = await request.body()
    name = ""
    if body:
        try:
            params = json.loads(body.decode("utf-8"))
            name = str(params.get("name") or "")
        except Exception:
            pass
    store = get_history_store()
    sid = await store.create_conversation(name or "新会话")
    conv = await store.get_conversation(sid)
    return {"ok": True, "session": conv}


@router.get("/sessions", response_model=SessionListResponse)
async def sessions_list():
    from core.session.history import get_history_store
    return {"ok": True, "sessions": await get_history_store().list_conversations()}


@router.patch("/sessions/{sid}", response_model=ApiResponse)
async def sessions_rename(sid: str, request: Request):
    from core.session.history import get_history_store
    body = await request.body()
    try:
        params = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        return JSONResponse({"ok": False, "error": "无效 JSON"}, status_code=400)
    name = (params.get("name") or "").strip()
    if not name:
        return JSONResponse({"ok": False, "error": "name 必填"}, status_code=400)
    await get_history_store().rename_conversation(sid, name)
    return {"ok": True}


@router.delete("/sessions/{sid}", response_model=ApiResponse)
async def sessions_delete(sid: str):
    from core.session.history import get_history_store
    await get_history_store().delete(sid)
    return {"ok": True}
