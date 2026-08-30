# -*- coding: utf-8 -*-
"""tools 域 API — 工具清单 / 单工具执行"""
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core.api.schemas import ToolCallResponse, ToolsResponse
from core.logger import logger
from core.tools import TOOLS

router = APIRouter()


@router.get("/tools", response_model=ToolsResponse)
async def tools_list():
    """工具清单：后端 @tool 注册中心的 OpenAI schema 数组（供控制台展示）。"""
    return {"ok": True, "tools": TOOLS.schemas()}


@router.post("/tools/call", response_model=ToolCallResponse)
async def tools_call(request: Request):
    body = await request.body()
    try:
        params = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        return JSONResponse({"ok": False, "error": "无效 JSON"}, status_code=400)
    name = params.get("name", "")
    args = params.get("args") or {}
    if not isinstance(name, str) or not name:
        return JSONResponse({"ok": False, "error": "缺少工具名 name"}, status_code=400)
    if not isinstance(args, dict):
        return JSONResponse({"ok": False, "error": "args 必须为 JSON 对象"}, status_code=400)
    if not TOOLS.has(name):
        return JSONResponse({"ok": False, "error": f"未知工具: {name}"}, status_code=404)
    # 非 read 工具需显式确认（前端弹窗后带 confirm: true 重调）
    risk = TOOLS.risk(name)
    if risk != "read" and not params.get("confirm"):
        return JSONResponse({
            "ok": False,
            "error": f"工具 {name} 属于 {risk} 风险，需要操作者显式确认",
            "needs_confirm": True,
        })
    try:
        result = await TOOLS.acall(name, args)
    except Exception as exc:
        logger.error("tools_call {}: {}", name, exc)
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    status = "error" if result.startswith("Error") else "ok"
    return {"ok": True, "status": status, "output": result}
