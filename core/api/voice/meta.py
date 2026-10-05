# -*- coding: utf-8 -*-
"""ping 与配置快照端点。Ping and config-snapshot endpoints."""
from fastapi import APIRouter

from core import config as config
from core.api.schemas import ConfigResponse, PingResponse

router = APIRouter()


@router.get("/ping", response_model=PingResponse)
async def ping():
    """心跳：返回当前服务器时间。

    Heartbeat: return the current server time.

    Returns:
        {"ok": True, "time": ISO 时间戳}。{"ok": True, "time": ISO timestamp}.
    """
    from datetime import datetime
    return {"ok": True, "time": datetime.now().isoformat()}

@router.get("/config", response_model=ConfigResponse)
async def config_endpoint():
    """返回前端启动所需的语音/模型配置快照（可用性 + 当前 profile + 语音参数）。

    Return the voice/model config snapshot needed by the frontend on startup
    (availability + current profile + voice parameters).

    Returns:
        配置字典。The config dict.
    """
    return {
        "llm_available": config.is_llm_configured(),
        "llm_profile": config.resolve_llm_profile()[0],
        "asr_available": config.is_asr_configured(),
        "asr_profile": config.resolve_asr_profile()[0],
        "tts_available": config.is_tts_enabled(),
        "tts_profile": config.resolve_tts_profile()[0],
        "tts_voice": config.resolve_tts_profile()[1].get("voice", ""),
        "tts_model": config.resolve_tts_profile()[1].get("model", ""),
        "wake_word": config.settings.voice.wake_word.model_dump(),
        "vad": config.settings.voice.vad.model_dump(),
        "call": config.settings.voice.call.model_dump(),
    }
