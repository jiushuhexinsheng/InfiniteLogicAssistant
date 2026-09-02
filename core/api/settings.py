# -*- coding: utf-8 -*-
"""settings 域 API — 配置读写 / 检测（设置页数据源）

settings domain API — config read/write & detection (settings-page data source)

GET   /api/config/full       可编辑配置快照（不含密钥值，密钥以 *_set 布尔暴露）
PATCH /api/config            持久化非敏感配置并热重载（per-request 立即生效；server 绑定类需重启）
PUT   /api/config/secrets    设置/清除密钥（写 config.secrets.yaml，永不回显）
GET   /api/detection         环境感知 + 配置校验 + LLM/ASR/TTS 连通性 聚合检测

GET   /api/config/full       editable config snapshot (no secret values; secrets exposed as *_set booleans)
PATCH /api/config            persist non-sensitive config & hot-reload (effective per-request; server-bound keys need restart)
PUT   /api/config/secrets    set/clear secrets (writes config.secrets.yaml, never echoed back)
GET   /api/detection         aggregated detection: environment + config validation + LLM/ASR/TTS connectivity
"""
import json

import yaml
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from core import config as config_mod
from core.api.schemas import (
    ConfigFullResponse, DetectionResponse, PatchConfigResponse, PutSecretsResponse,
)
from core.detection import run_all
from core.logger import logger

router = APIRouter()


# ─────────────────────────── 工具 ───────────────────────────


def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并两个字典：override 的键覆盖 base，嵌套 dict 递归合并。

    Recursively merge two dicts: keys from override overwrite base, nested dicts are merged recursively.

    Args:
        base: 基础字典，会被复制而非原地修改。The base dict, copied rather than mutated.
        override: 覆盖字典。The overriding dict.

    Returns:
        合并后的新字典。The merged new dict.
    """
    result = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _normalize_patch(patch: dict) -> dict:
    """把前端快照的顶层 asr/tts/wake_word/vad 归一到 voice 段下（对齐 config.yaml 结构）。

    前端 editable_snapshot 把这些键平铺在顶层，但 Settings 模型里它们嵌在 voice 下
    （extra=forbid 会拒绝顶层多余键）。历史遗留：此前保存 ASR/TTS/语音设置会 400。

    Normalize top-level asr/tts/wake_word/vad keys from the frontend snapshot into the
    voice section (matching the config.yaml structure). The frontend editable_snapshot
    flattens these keys at the top level, but the Settings model nests them under voice
    (extra=forbid would reject unknown top-level keys). Legacy: saving ASR/TTS/voice
    settings used to return 400.
    """
    voice: dict = {}
    for key in ("asr", "tts", "wake_word", "vad"):
        if key in patch:
            voice[key] = patch.pop(key)
    if voice:
        patch["voice"] = _deep_merge(patch.get("voice") or {}, voice)
    return patch


def _wholesale_profiles(merged: dict, patch: dict) -> None:
    """前端整份提交 profiles Record → patch 里出现的 profiles 段整体替换。

    _deep_merge 只遍历 override 的 key，删除的 profile 不会被移除；这里对 patch
    中出现的 profiles 做整体替换，让「删除 profile」真正生效。

    When the frontend submits a full profiles record, wholesale-replace any profiles
    section present in the patch. _deep_merge only iterates override keys, so deleted
    profiles would never be removed; replacing the whole profiles section makes
    "delete profile" actually take effect.
    """
    llm = patch.get("llm")
    if isinstance(llm, dict) and isinstance(llm.get("profiles"), dict) and isinstance(merged.get("llm"), dict):
        merged["llm"]["profiles"] = llm["profiles"]
    vpatch = patch.get("voice")
    voice_patch = vpatch if isinstance(vpatch, dict) else {}
    voice_merged = merged.setdefault("voice", {})
    for key in ("asr", "tts"):
        sec = voice_patch.get(key)
        if isinstance(sec, dict) and isinstance(sec.get("profiles"), dict) and isinstance(voice_merged.get(key), dict):
            voice_merged[key]["profiles"] = sec["profiles"]


def _strip_secrets(d):
    """递归移除 api_key / api_token：密钥只能走 secrets 接口。

    Recursively remove api_key / api_token: secrets may only go through the secrets endpoint.
    """
    if isinstance(d, dict):
        d.pop("api_key", None)
        d.pop("api_token", None)
        for v in d.values():
            _strip_secrets(v)
    elif isinstance(d, list):
        for item in d:
            _strip_secrets(item)


def _needs_restart(old: dict, new: dict) -> bool:
    """server 绑定类（host/port/open_browser/cors_origins）或 MCP 变化 → 需重启。

    True when server-bound settings (host/port/open_browser/cors_origins) or MCP
    config change → a restart is required.
    """
    old_srv, new_srv = old.get("server") or {}, new.get("server") or {}
    for key in ("host", "port", "open_browser", "cors_origins"):
        if old_srv.get(key) != new_srv.get(key):
            return True
    if (old.get("mcp") or {}) != (new.get("mcp") or {}):
        return True
    return False


def _fmt_validation(e: ValidationError) -> str:
    """把 Pydantic ValidationError 格式化为可读的一行字符串。

    Format a Pydantic ValidationError into a readable one-line string.

    Args:
        e: Pydantic 校验错误。The Pydantic validation error.

    Returns:
        “路径: 消息 (类型)” 条目的分号拼接。Semicolon-joined "loc: msg (type)" entries.
    """
    return "; ".join(
        f"{'.'.join(str(x) for x in err['loc']) or '(root)'}: {err['msg']} ({err['type']})"
        for err in e.errors()
    )


def _read_json_body(body: bytes):
    """解析请求体 JSON；空体视为 {}，解析失败或非对象时返回 None。

    Parse the request body JSON; an empty body is treated as {}, and None is
    returned when parsing fails or the payload is not an object.

    Args:
        body: 原始请求字节。Raw request bytes.

    Returns:
        解析后的 dict，或 None。The parsed dict, or None.
    """
    try:
        data = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        return None
    return data if isinstance(data, dict) else None


# ─────────────────────────── 端点 ───────────────────────────


@router.get("/config/full", response_model=ConfigFullResponse)
async def config_full():
    """设置页可编辑快照（密钥不回显）。

    Editable snapshot for the settings page (secrets are not echoed back).
    """
    return {"ok": True, "editable": config_mod.editable_snapshot()}


@router.patch("/config", response_model=PatchConfigResponse)
async def patch_config(request: Request):
    """持久化非敏感配置并热重载；server 绑定类 / MCP 变更返回 restart_required=true。

    Persist non-sensitive config and hot-reload; returns restart_required=true when
    server-bound settings or the MCP config changed.
    """
    patch = _read_json_body(await request.body())
    if patch is None:
        return JSONResponse({"ok": False, "error": "请求体必须是 JSON 对象"}, status_code=400)

    try:
        current = yaml.safe_load(config_mod.CONFIG_FILE.read_text(encoding="utf-8")) or {}
    except Exception:
        current = {}

    patch = _normalize_patch(patch)
    merged = _deep_merge(current, patch)
    _wholesale_profiles(merged, patch)
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


@router.put("/config/secrets", response_model=PutSecretsResponse)
async def put_secrets(request: Request):
    """设置/清除密钥（value 为空字符串=清除）。path 形如 llm.api_key / llm.profiles.deepseek / server.api_token。

    只写 config.secrets.yaml，永不把密钥值放进响应。

    Set/clear a secret (empty value string = clear). path looks like llm.api_key /
    llm.profiles.deepseek / server.api_token. Only writes config.secrets.yaml and never
    puts secret values into the response.
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


@router.get("/detection", response_model=DetectionResponse)
async def detection():
    """聚合检测：环境快照 + 配置健康 + 三项连通性（设置页「检测全部」按钮）。

    Aggregated detection: environment snapshot + config health + three connectivity
    checks (the "check all" button on the settings page).
    """
    try:
        report = await run_all()
        return {"ok": True, "report": report}
    except Exception as e:
        logger.error("detection 聚合失败: {}", e)
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
