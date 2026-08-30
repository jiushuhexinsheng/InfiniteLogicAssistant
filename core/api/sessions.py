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
async def sessions_list(archived: bool | None = None):
    """会话列表；?archived=true 只归档 / false(默认) 排除归档。"""
    from core.session.history import get_history_store
    flag = archived if archived is not None else False
    return {"ok": True, "sessions": await get_history_store().list_conversations(archived=flag)}


@router.patch("/sessions/{sid}", response_model=ApiResponse)
async def sessions_patch(sid: str, request: Request):
    """更新会话：body {name} 重命名 或 {archived: bool} 归档/取消归档（可同时）。"""
    from core.session.history import get_history_store
    body = await request.body()
    try:
        params = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        return JSONResponse({"ok": False, "error": "无效 JSON"}, status_code=400)
    if not isinstance(params, dict) or not (params.get("name") or params.get("archived") is not None):
        return JSONResponse({"ok": False, "error": "需提供 name 或 archived"}, status_code=400)
    store = get_history_store()
    if "name" in params:
        name = (params.get("name") or "").strip()
        if not name:
            return JSONResponse({"ok": False, "error": "name 必填"}, status_code=400)
        await store.rename_conversation(sid, name)
    if params.get("archived") is not None:
        await store.set_archived(sid, bool(params.get("archived")))
    return {"ok": True}


@router.post("/sessions/{sid}/clear", response_model=ApiResponse)
async def sessions_clear(sid: str):
    """清除上下文：清空该会话消息（会话记录与 name 保留）。"""
    from core.session.history import get_history_store
    await get_history_store().clear_messages(sid)
    return {"ok": True}


@router.delete("/sessions/{sid}", response_model=ApiResponse)
async def sessions_delete(sid: str):
    from core.session.history import get_history_store
    await get_history_store().delete(sid)
    return {"ok": True}
