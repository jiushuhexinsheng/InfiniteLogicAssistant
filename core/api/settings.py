# -*- coding: utf-8 -*-
"""settings 域 API — 配置读写 / 检测（设置页数据源）

GET   /api/config/full       可编辑配置快照（不含密钥值，密钥以 *_set 布尔暴露）
PATCH /api/config            持久化非敏感配置并热重载（per-request 立即生效；server 绑定类需重启）
PUT   /api/config/secrets    设置/清除密钥（写 config.secrets.yaml，永不回显）
GET   /api/detection         环境感知 + 配置校验 + LLM/ASR/TTS 连通性 聚合检测
"""
import json

import yaml
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from core import config as config_mod
from core.detection import run_all
from core.logger import logger

router = APIRouter()


# ─────────────────────────── 工具 ───────────────────────────


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _strip_secrets(d):
    """递归移除 api_key / api_token：密钥只能走 secrets 接口。"""
    if isinstance(d, dict):
        d.pop("api_key", None)
        d.pop("api_token", None)
        for v in d.values():
            _strip_secrets(v)
    elif isinstance(d, list):
        for item in d:
            _strip_secrets(item)


def _needs_restart(old: dict, new: dict) -> bool:
    """server 绑定类（host/port/open_browser/cors_origins）或 MCP 变化 → 需重启。"""
    old_srv, new_srv = old.get("server") or {}, new.get("server") or {}
    for key in ("host", "port", "open_browser", "cors_origins"):
        if old_srv.get(key) != new_srv.get(key):
            return True
    if (old.get("mcp") or {}) != (new.get("mcp") or {}):
        return True
    return False


def _fmt_validation(e: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(x) for x in err['loc']) or '(root)'}: {err['msg']} ({err['type']})"
        for err in e.errors()
    )


def _read_json_body(body: bytes):
    try:
        data = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        return None
    return data if isinstance(data, dict) else None


# ─────────────────────────── 端点 ───────────────────────────


@router.get("/config/full")
async def config_full():
    """设置页可编辑快照（密钥不回显）。"""
    return {"ok": True, "editable": config_mod.editable_snapshot()}


@router.patch("/config")
async def patch_config(request: Request):
    """持久化非敏感配置并热重载；server 绑定类 / MCP 变更返回 restart_required=true。"""
    patch = _read_json_body(await request.body())
    if patch is None:
        return JSONResponse({"ok": False, "error": "请求体必须是 JSON 对象"}, status_code=400)

    try:
        current = yaml.safe_load(config_mod.CONFIG_FILE.read_text(encoding="utf-8")) or {}
    except Exception:
        current = {}

    merged = _deep_merge(current, patch)
    _strip_secrets(merged)
    try:
        config_mod.Settings(**merged)  # 校验：类型/范围/未知字段 违规即 400
    except ValidationError as e:
        return JSONResponse({"ok": False, "error": f"配置无效: {_fmt_validation(e)}"}, status_code=400)

    restart_required = _needs_restart(current, merged)
    try:
        with open(config_mod.CONFIG_FILE, "w", encoding="utf-8") as f:
            yaml.safe_dump(merged, f, allow_unicode=True, sort_keys=False)
    except Exception as e:
        logger.error("写回 config.yaml 失败: {}", e)
        return JSONResponse({"ok": False, "error": f"写入 config.yaml 失败: {e}"}, status_code=500)

    config_mod.reload_settings()  # 热重载：per-request 读取立即生效
    return {"ok": True, "restart_required": restart_required}


@router.put("/config/secrets")
async def put_secrets(request: Request):
    """设置/清除密钥（value 为空字符串=清除）。path 形如 llm.api_key / llm.profiles.deepseek / server.api_token。

    只写 config.secrets.yaml，永不把密钥值放进响应。
    """
    body = _read_json_body(await request.body())
    if body is None:
        return JSONResponse({"ok": False, "error": "请求体必须是 JSON 对象"}, status_code=400)
    path = str(body.get("path") or "")
    value = str(body.get("value") or "")
    parts = [p for p in path.split(".") if p]
    if not parts or parts[0] not in ("llm", "asr", "tts", "server"):
        return JSONResponse({"ok": False, "error": f"无效的密钥路径: {path}"}, status_code=400)
    if parts[0] == "server" and parts != ["server", "api_token"]:
        return JSONResponse({"ok": False, "error": "server 只支持 api_token"}, status_code=400)
    if parts[0] != "server" and len(parts) not in (2, 3):
        return JSONResponse({"ok": False, "error": f"路径需为 <段>.api_key 或 <段>.profiles.<名>: {path}"}, status_code=400)

    # 读现有 secrets → 按路径写入 → 写回
    try:
        data = yaml.safe_load(config_mod.SECRETS_FILE.read_text(encoding="utf-8")) or {}
    except Exception:
        data = {}
    node = data.setdefault(parts[0], {})
    if len(parts) == 3:  # llm.profiles.deepseek
        profs = node.setdefault("profiles", {})
        profs[parts[2]] = value if value else None
        if not value:
            profs.pop(parts[2], None)
    else:  # llm.api_key / server.api_token
        node["api_key" if parts[0] != "server" else "api_token"] = value
    if isinstance(node, dict) and not node.get("profiles"):
        node.pop("profiles", None)
    with open(config_mod.SECRETS_FILE, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

    config_mod.reload_settings()
    return {"ok": True, "set": bool(value), "path": path}


@router.get("/detection")
async def detection():
    """聚合检测：环境快照 + 配置健康 + 三项连通性（设置页「检测全部」按钮）。"""
    try:
        report = await run_all()
        return {"ok": True, "report": report}
    except Exception as e:
        logger.error("detection 聚合失败: {}", e)
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
