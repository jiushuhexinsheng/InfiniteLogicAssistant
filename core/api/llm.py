# -*- coding: utf-8 -*-
"""LLM 模型清单与全局模型切换端点。

GET  /api/llm/models       按供应商分组的可用模型（供对话内切换器）
POST /api/llm/active-model 设置全局 active 供应商与模型（专用端点，避免 PATCH 整段替换 profiles）

LLM catalogue and global model switching:
GET returns models grouped by provider; POST sets the global active provider/model.
A dedicated endpoint is used because PATCH /api/config wholesale-replaces the
profiles mapping, which would delete every other provider when only one model is sent.
"""
import json

import yaml
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from core import config as config_mod
from core.api.schemas.llm import (
    LlmActive,
    LlmModelGroup,
    LlmModelsResponse,
    SetActiveModelRequest,
    SetActiveModelResponse,
)
from core.logger import logger

router = APIRouter()


def _models_of(profile: object) -> list[str]:
    """profile 的可用模型集合：models ∪ 当前 model，去空去重保序。

    The profile's selectable models: models ∪ current model, trimmed and de-duplicated
    while preserving order.

    Args:
        profile: profile 对象或原始 dict。A profile object or raw dict.

    Returns:
        模型 id 列表。Model-id list.
    """
    if isinstance(profile, dict):
        listed = profile.get("models") or []
        current = profile.get("model") or ""
    else:
        listed = getattr(profile, "models", None) or []
        current = getattr(profile, "model", "") or ""
    out: list[str] = []
    for value in [*listed, current]:
        text = str(value or "").strip()
        if text and text not in out:
            out.append(text)
    return out


@router.get("/llm/models", response_model=LlmModelsResponse)
async def llm_models():
    """按供应商分组返回可用模型与当前全局选择。

    Return selectable models grouped by provider plus the current global selection.

    Returns:
        LlmModelsResponse。The grouped catalogue.
    """
    active_name, active_profile = config_mod.resolve_llm_profile()
    groups = [
        LlmModelGroup(
            provider=provider,
            label=provider,
            models=_models_of(profile),
            current_model=str(getattr(profile, "model", "") or ""),
        )
        for provider, profile in config_mod.get_settings().llm.profiles.items()
    ]
    return LlmModelsResponse(
        active=LlmActive(provider=active_name,
                         model=str(active_profile.get("model", "") or "")),
        groups=groups,
    )


@router.post("/llm/active-model", response_model=SetActiveModelResponse)
async def set_active_model(request: Request):
    """设置全局使用的供应商与模型并热重载。

    Set the globally used provider/model and hot-reload the configuration.

    Args:
        request: 请求体 `{"provider": str, "model": str}`。Request body.

    Returns:
        新的 active 选择；非法输入返回 400。The new selection; 400 on invalid input.
    """
    try:
        body = json.loads((await request.body()).decode("utf-8") or "{}")
        req = SetActiveModelRequest(**body)
    except (ValueError, TypeError, ValidationError):
        return JSONResponse({"ok": False, "error": "请求体需为 {provider, model}"},
                            status_code=400)
    provider = req.provider.strip()
    model = req.model.strip()
    if not provider or not model:
        return JSONResponse({"ok": False, "error": "provider/model 不能为空"},
                            status_code=400)

    try:
        data = yaml.safe_load(config_mod.CONFIG_FILE.read_text(encoding="utf-8")) or {}
    except Exception:
        data = {}
    llm = data.get("llm") if isinstance(data, dict) else None
    profiles = (llm or {}).get("profiles") if isinstance(llm, dict) else None
    profile = profiles.get(provider) if isinstance(profiles, dict) else None
    if not isinstance(profile, dict):
        return JSONResponse({"ok": False, "error": f"供应商不存在: {provider}"},
                            status_code=400)
    if model not in _models_of(profile):
        return JSONResponse(
            {"ok": False, "error": f"模型 {model} 不在供应商 {provider} 的模型列表中"},
            status_code=400,
        )

    if not isinstance(llm, dict):
        return JSONResponse({"ok": False, "error": "配置缺少 llm 段"}, status_code=400)
    llm["active"] = provider
    profile["model"] = model
    try:
        config_mod.Settings(**data)  # 类型/范围/未知字段校验。
    except ValidationError as e:
        return JSONResponse({"ok": False, "error": f"配置无效: {e.errors()[0]['msg']}"},
                            status_code=400)
    try:
        config_mod.CONFIG_FILE.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    except OSError as e:
        logger.error("写入 config.yaml 失败: {}", e)
        return JSONResponse({"ok": False, "error": f"写入配置失败: {e}"}, status_code=500)

    config_mod.reload_settings(source="api.llm_model")
    return SetActiveModelResponse(active=LlmActive(provider=provider, model=model))
