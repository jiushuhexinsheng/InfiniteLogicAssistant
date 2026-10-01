# -*- coding: utf-8 -*-
"""TTS 合成端点(返回音频字节,不走 response_model)。

TTS synthesis endpoint (returns audio bytes; no response_model).
"""
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from core import config as config
from core.logger import logger

router = APIRouter()


@router.post("/tts")
async def tts_synthesize(request: Request):
    """文本转语音：调后端配置的 OpenAI 兼容 TTS 端点，返回音频字节。

    请求体：{"text": "...", "voice": "可选，缺省用配置里的 voice"}

    Text-to-speech: call the backend-configured OpenAI-compatible TTS endpoint and
    return the audio bytes. Request body: {"text": "...", "voice": "optional,
    defaults to the voice from config"}
    """
    body = await request.body()
    try:
        params = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        return JSONResponse({"ok": False, "error": "无效 JSON"}, status_code=400)
    text = (params.get("text") or "").strip()
    voice = params.get("voice") or None
    if not text:
        return JSONResponse({"ok": False, "error": "text 不能为空"}, status_code=400)
    if not config.is_tts_enabled():
        return JSONResponse(
            {"ok": False, "error": "TTS 未启用：voice.tts.enabled=false 或未配置 endpoint"},
            status_code=400,
        )
    try:
        from core.voice.tts import synthesize
        from core.voice.tts import TtsConfigError
        audio, media_type = await synthesize(text, voice)
    except TtsConfigError as e:
        # 配置问题（未启用/缺 voice_ref 等）：客户端可修复 → 400
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    except Exception as e:
        logger.warning("TTS 合成失败: {}", e)
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
    return Response(content=audio, media_type=media_type)
