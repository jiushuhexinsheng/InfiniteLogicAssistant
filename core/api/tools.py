# -*- coding: utf-8 -*-
"""tools 域 API — 工具清单 / 单工具执行

tools domain API — tool listing / single-tool invocation
"""
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core.api.schemas import ToolCallResponse, ToolsResponse
from core.logger import logger
from core.tools import TOOLS
from core.tools.policy import decide

router = APIRouter()


@router.get("/tools", response_model=ToolsResponse)
async def tools_list():
    """工具清单：后端 @tool 注册中心的 OpenAI schema 数组（供控制台展示）。

    Tool listing: OpenAI schemas from the backend @tool registry (for console display).
    """
    return {"ok": True, "tools": TOOLS.schemas()}


@router.post("/tools/call", response_model=ToolCallResponse)
async def tools_call(request: Request):
    """执行单个工具：校验 name/args、非 read 工具需显式确认、返回执行输出。

    Invoke a single tool: validate name/args, require explicit confirmation for
    non-read tools, and return the execution output.

    Args:
        request: FastAPI 请求，JSON 体为 {name, args, confirm?}。The FastAPI request
            with a JSON body of {name, args, confirm?}.

    Returns:
        执行结果 {ok, status, output}，或错误 JSONResponse。The execution result
        {ok, status, output}, or an error JSONResponse.
    """
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
    # 由权限策略决定：deny 直接 403（confirm 不能覆盖 deny）；ask 需 confirm 标记；
    # allow 直接执行。
    # The permission policy decides: deny returns 403 (confirm cannot override it); ask
    # requires the confirm flag; allow runs directly.
    decision = decide(name)
    if decision.action == "deny":
        return JSONResponse(
            {"ok": False, "error": f"操作者策略禁止调用 {name}（{decision.source}）"},
            status_code=403,
        )
    if decision.action == "ask" and not params.get("confirm"):
        return JSONResponse({
            "ok": False,
            "error": f"工具 {name} 需要操作者确认（{decision.source}）",
            "needs_confirm": True,
        })
    try:
        result = await TOOLS.acall(name, args)
    except Exception as exc:
        logger.error("tools_call {}: {}", name, exc)
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    status = "error" if result.startswith("Error") else "ok"
    return {"ok": True, "status": status, "output": result}
