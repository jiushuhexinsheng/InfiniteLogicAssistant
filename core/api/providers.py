# -*- coding: utf-8 -*-
"""providers 域 API — 厂商目录 + 获取模型列表

GET  /api/providers              合并后厂商目录（代码内置 + YAML 扩展），按 kind 分组，无密钥
POST /api/providers/fetch-models 服务端调 OpenAI 兼容 GET {endpoint}{models_path}/models
                                  拉模型列表（密钥只用于转发，永不回显）
"""
import json

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core import config as config_mod
from core.logger import logger
from core.providers import get_presets_by_kind, models_path_for, resolve_protocol, to_public_dict

router = APIRouter()

_MODEL_LIMIT = 200  # 模型列表上限，避免写爆 config.yaml


@router.get("/providers")
async def list_providers():
    catalog: dict = {}
    for kind in ("llm", "asr", "tts"):
        catalog[kind] = [
            {"id": pid, **to_public_dict(preset.model_dump())}
            for pid, preset in get_presets_by_kind(kind)
        ]
    return {"ok": True, "catalog": catalog}


@router.post("/providers/fetch-models")
async def fetch_models(request: Request):
    """拉取某 profile 的可用模型列表（仅 OpenAI 兼容协议）。

    请求体：{"section": "llm|asr|tts", "profile": {完整 profile dict，含 name/endpoint/chat_path/api_key_env}}
    profile 传完整 dict，未保存的新 profile 也能测（密钥由服务端按优先级解析，不回显）。
    """
    body = _read_json(await request.body())
    if body is None:
        return JSONResponse({"ok": False, "error": "请求体必须是 JSON 对象"}, status_code=400)
    section = str(body.get("section") or "")
    profile = body.get("profile")
    if section not in ("llm", "asr", "tts"):
        return JSONResponse({"ok": False, "error": f"无效的 section: {section}"}, status_code=400)
    if not isinstance(profile, dict):
        return JSONResponse({"ok": False, "error": "profile 必须是对象"}, status_code=400)

    if resolve_protocol(profile) != "openai":
        return JSONResponse({"ok": False, "error": "仅 OpenAI 兼容协议支持获取模型列表"}, status_code=400)
    api_key = config_mod.profile_api_key(section, str(profile.get("name") or ""), profile)
    if not api_key:
        return JSONResponse({"ok": False, "error": "未配置 API Key，无法获取模型列表"}, status_code=400)
    endpoint = (profile.get("endpoint") or "").rstrip("/")
    if not endpoint:
        return JSONResponse({"ok": False, "error": "缺少 endpoint"}, status_code=400)

    path = models_path_for(profile)
    timeout = float(profile.get("timeout") or 30)
    try:
        models = await _fetch_models(endpoint, path, api_key, timeout)
    except Exception as e:
        logger.warning("fetch-models 失败: {}", e)
        return JSONResponse({"ok": False, "error": f"获取模型列表失败: {e}"}, status_code=502)
    return {"ok": True, "models": models, "count": len(models)}


async def _fetch_models(endpoint: str, path: str, api_key: str, timeout: float) -> list[str]:
    """GET {endpoint}{path}/models → 模型 id 列表（去重排序，截断 _MODEL_LIMIT）。"""
    url = f"{endpoint}{path if path.startswith('/') else '/' + path}"
    headers = {"Authorization": f"Bearer {api_key}"}
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    out: list[str] = []
    for item in data.get("data") or []:
        mid = item.get("id") if isinstance(item, dict) else item
        if isinstance(mid, str) and mid:
            out.append(mid)
    return sorted(set(out))[:_MODEL_LIMIT]


def _read_json(body: bytes):
    try:
        data = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        return None
    return data if isinstance(data, dict) else None
