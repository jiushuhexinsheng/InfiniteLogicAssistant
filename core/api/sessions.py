# -*- coding: utf-8 -*-
"""sessions 域 API — 会话管理（新建 / 列表 / 重命名 / 删除）

会话 = 可续接对话线（history.db 的 conversations 记录，含 name）；对话续接走
POST /api/voice/utter 的 session_id 参数。

Sessions domain API — session management (create / list / rename / delete).

A session is a resumable conversation thread (a conversations record in history.db, with a name);
conversation resumption goes through the session_id parameter of POST /api/voice/utter.
"""
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core.api.schemas import ApiResponse, SessionCreateResponse, SessionListResponse

router = APIRouter()


@router.post("/sessions/{sid}/fork", response_model=SessionCreateResponse)
async def sessions_fork(sid: str, request: Request):
    """分叉会话：body {"up_to": <消息下标, 含该条>} → 复制前缀为新会话（源不动）。

    - 源不存在 → 404；up_to 越界 → 400；源会话正等待回答 → 409（进行中的 run 不可分叉）。
    - 编辑重发/重新生成必须先分叉（整段覆盖存储下直接改写会丢原路径，docs/designs/07）。

    Fork a session: body {"up_to": <message index, inclusive>} copies the prefix into a
    new conversation (the source is untouched). Missing source → 404; up_to out of
    range → 400; the source is waiting for an answer → 409 (no forking a live run).
    Edit-and-resend must fork first (whole-overwrite storage would destroy the
    original path, docs/designs/07).
    """
    from core.api import state
    from core.logger import audit
    from core.session.history import get_history_store

    body = await request.body()
    try:
        params = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        return JSONResponse({"ok": False, "error": "无效 JSON"}, status_code=400)
    up_to = params.get("up_to")
    if not isinstance(up_to, int) or isinstance(up_to, bool):
        return JSONResponse({"ok": False, "error": "up_to 必须是整数消息下标"}, status_code=400)

    live = state.get_session(sid)
    live_channel = getattr(live, "channel", None) if live else None
    if live_channel is not None and getattr(live_channel, "awaiting_answer", False):
        return JSONResponse({"ok": False, "error": "会话正在等待回答，无法分叉"}, status_code=409)

    store = get_history_store()
    conv = await store.get_conversation(sid)
    if conv is None:
        return JSONResponse({"ok": False, "error": "会话不存在"}, status_code=404)
    n = len(conv.get("messages") or [])
    if n == 0 or up_to < 0 or up_to >= n:
        return JSONResponse({"ok": False, "error": f"up_to 越界（0..{n - 1}）"}, status_code=400)

    new_id = await store.fork_conversation(sid, up_to)
    if new_id is None:
        return JSONResponse({"ok": False, "error": "分叉失败"}, status_code=500)
    audit(f"session-fork from={sid} to={new_id} up_to={up_to} n={n}")
    return {"ok": True, "session": await store.get_conversation(new_id)}


@router.post("/sessions", response_model=SessionCreateResponse)
async def sessions_create(request: Request):
    """新建会话（可选 body {"name"}；缺省名「新会话」），返回 {id, name, ...}。

    Create a new session (optional body {"name"}; defaults to "新会话"), returns {id, name, ...}.
    """
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
    """会话列表；?archived=true 只归档 / false(默认) 排除归档。

    List sessions; ?archived=true returns only archived ones, false (default) excludes archived.
    """
    from core.session.history import get_history_store
    flag = archived if archived is not None else False
    return {"ok": True, "sessions": await get_history_store().list_conversations(archived=flag)}


@router.patch("/sessions/{sid}", response_model=ApiResponse)
async def sessions_patch(sid: str, request: Request):
    """更新会话：body {name} 重命名 或 {archived: bool} 归档/取消归档（可同时）。

    Update a session: body {name} renames or {archived: bool} archives/unarchives (both allowed at once).
    """
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
    """清除上下文：清空该会话消息（会话记录与 name 保留）。

    Clear the context: wipe the session's messages (the session record and its name are kept).
    """
    from core.session.history import get_history_store
    await get_history_store().clear_messages(sid)
    return {"ok": True}


@router.delete("/sessions/{sid}", response_model=ApiResponse)
async def sessions_delete(sid: str):
    """删除指定会话（含其全部消息）。

    Delete the specified session (including all of its messages).
    """
    from core.session.history import get_history_store
    await get_history_store().delete(sid)
    return {"ok": True}
