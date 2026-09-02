# -*- coding: utf-8 -*-
"""providers 域 API — 厂商目录 + 获取模型列表

GET  /api/providers              合并后厂商目录（代码内置 + YAML 扩展），按 kind 分组，无密钥
POST /api/providers/fetch-models 服务端调 OpenAI 兼容 GET {endpoint}{models_path}/models
                                  拉模型列表（密钥只用于转发，永不回显）

GET  /api/providers              merged vendor catalog (built-in + YAML extension), grouped by kind, no secrets
POST /api/providers/fetch-models server calls the OpenAI-compatible GET {endpoint}{models_path}/models
                                  to fetch the model list (keys are only forwarded, never echoed)
"""
import json

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core import config as config_mod
from core.api.schemas import CatalogResponse, FetchModelsResponse
from core.logger import logger
from core.vendors import get_presets_by_kind, models_path_for, resolve_protocol, to_public_dict

router = APIRouter()

_MODEL_LIMIT = 200  # 模型列表上限，避免写爆 config.yaml


@router.get("/providers", response_model=CatalogResponse)
async def list_providers():
    """返回合并后的厂商目录，按 kind（llm/asr/tts）分组，不含密钥。

    Return the merged vendor catalog grouped by kind (llm/asr/tts), without secrets.
    """
    catalog: dict = {}
    for kind in ("llm", "asr", "tts"):
        catalog[kind] = [
            {"id": pid, **to_public_dict(preset.model_dump())}
            for pid, preset in get_presets_by_kind(kind)
        ]
    return {"ok": True, "catalog": catalog}


@router.post("/providers/fetch-models", response_model=FetchModelsResponse)
async def fetch_models(request: Request):
    """拉取某 profile 的可用模型列表（按协议分派：openai / anthropic / gemini）。

    请求体：{"section": "llm|asr|tts", "profile": {完整 profile dict，含 name/endpoint/chat_path/api_key_env}}
    profile 传完整 dict，未保存的新 profile 也能测（密钥由服务端按优先级解析，不回显）。

    Fetch the available model list for a profile (dispatched by protocol: openai / anthropic / gemini).

    Request body: {"section": "llm|asr|tts", "profile": {full profile dict incl. name/endpoint/chat_path/api_key_env}}
    The full profile dict is passed in, so an unsaved new profile can also be tested
    (the key is resolved server-side by priority and never echoed).
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

    api_key = config_mod.profile_api_key(section, str(profile.get("name") or ""), profile)
    if not api_key:
        return JSONResponse({"ok": False, "error": "未配置 API Key，无法获取模型列表"}, status_code=400)
    endpoint = (profile.get("endpoint") or "").rstrip("/")
    if not endpoint:
        return JSONResponse({"ok": False, "error": "缺少 endpoint"}, status_code=400)

    try:
        models = await _fetch_models(profile, api_key)
    except Exception as e:
        logger.warning("fetch-models 失败: {}", e)
        return JSONResponse({"ok": False, "error": f"获取模型列表失败: {e}"}, status_code=502)
    return {"ok": True, "models": models, "count": len(models)}


async def _fetch_models(profile: dict, api_key: str, *, client: httpx.AsyncClient | None = None) -> list[str]:
    """按协议拉取模型列表（去重排序，截断 _MODEL_LIMIT）：
    openai → GET {endpoint}{models_path}/models；anthropic → GET {endpoint}/v1/models（x-api-key）；
    gemini → GET {endpoint}/v1beta/models（x-goog-api-key，仅 generateContent 模型，剥 models/ 前缀）。

    Fetch the model list per protocol (deduplicated, sorted, truncated to _MODEL_LIMIT):
    openai → GET {endpoint}{models_path}/models; anthropic → GET {endpoint}/v1/models (x-api-key);
    gemini → GET {endpoint}/v1beta/models (x-goog-api-key, generateContent models only, strips the models/ prefix).
    """
    protocol = resolve_protocol(profile)
    endpoint = (profile.get("endpoint") or "").rstrip("/")
    timeout = float(profile.get("timeout") or 30)

    own = None
    if client is None:
        own = httpx.AsyncClient(timeout=timeout)
        client = own
    try:
        if protocol == "anthropic":
            resp = await client.get(
                f"{endpoint}/v1/models",
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            )
            resp.raise_for_status()
            ids = [m.get("id") for m in (resp.json().get("data") or []) if isinstance(m, dict)]
            return _model_limit(ids)
        if protocol == "gemini":
            resp = await client.get(
                f"{endpoint}/v1beta/models",
                headers={"x-goog-api-key": api_key},
            )
            resp.raise_for_status()
            ids = []
            for m in resp.json().get("models") or []:
                if not isinstance(m, dict):
                    continue
                name = m.get("name") or ""
                if name.startswith("models/"):
                    name = name[len("models/"):]
                methods = m.get("supportedGenerationMethods") or []
                if name and "generateContent" in methods:
                    ids.append(name)
            return _model_limit(ids)
        # openai 兼容
        path = models_path_for(profile)
        url = f"{endpoint}{path if path.startswith('/') else '/' + path}"
        resp = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
        resp.raise_for_status()
        ids = [m.get("id") if isinstance(m, dict) else m for m in (resp.json().get("data") or [])]
        return _model_limit(ids)
    finally:
        if own is not None:
            await own.aclose()


def _model_limit(ids: list) -> list[str]:
    """清洗、去重并排序模型 ID 列表，截断到 _MODEL_LIMIT。

    Clean, deduplicate and sort the model ID list, truncated to _MODEL_LIMIT.
    """
    out = [str(i) for i in ids if isinstance(i, str) and i]
    return sorted(set(out))[:_MODEL_LIMIT]


def _read_json(body: bytes):
    """将请求体解析为 JSON 对象；空体或非对象内容返回 None。

    Parse the request body into a JSON object; return None for an empty body or a non-object.
    """
    try:
        data = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        return None
    return data if isinstance(data, dict) else None
