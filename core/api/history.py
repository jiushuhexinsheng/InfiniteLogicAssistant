# -*- coding: utf-8 -*-
"""history 域 API — 会话历史列表 / 详情 / 删除（控制台「历史」tab）"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/history")
async def history_list(limit: int = 30):
    from core.history import get_history_store
    return {"ok": True, "conversations": await get_history_store().list_conversations(limit)}


@router.get("/history/{conv_id}")
async def history_get(conv_id: str):
    from core.history import get_history_store
    conv = await get_history_store().get_conversation(conv_id)
    if not conv:
        return JSONResponse({"ok": False, "error": "会话不存在"}, status_code=404)
    return {"ok": True, "conversation": conv}


@router.delete("/history/{conv_id}")
async def history_delete(conv_id: str):
    from core.history import get_history_store
    await get_history_store().delete(conv_id)
    return {"ok": True}
