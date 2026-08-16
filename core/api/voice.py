# -*- coding: utf-8 -*-
"""voice 域 API — 配置 / TTS / ASR 转写 / 编排 SSE 入口（唯一 agent 路径）"""
import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from core import config as config
from core.api import state
from core.logger import logger

router = APIRouter()


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.get("/ping")
async def ping():
    from datetime import datetime
    return {"ok": True, "time": datetime.now().isoformat()}


@router.get("/config")
async def config_endpoint():
    return {
        "llm_available": config.is_llm_configured(),
        "llm_profile": config.resolve_llm_profile()[0],
        "asr_available": config.is_asr_configured(),
        "asr_profile": config.resolve_asr_profile()[0],
        "tts_available": config.is_tts_enabled(),
        "tts_profile": config.resolve_tts_profile()[0],
        "tts_voice": config.resolve_tts_profile()[1].get("voice", ""),
        "tts_model": config.resolve_tts_profile()[1].get("model", ""),
        "wake_word": config.cfg("voice.wake_word", {}),
        "vad": config.cfg("voice.vad", {}),
    }


@router.post("/tts")
async def tts_synthesize(request: Request):
    """文本转语音：调后端配置的 OpenAI 兼容 TTS 端点，返回音频字节。

    请求体：{"text": "...", "voice": "可选，缺省用配置里的 voice"}
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
        from core.tts import synthesize
        audio, media_type = await synthesize(text, voice)
    except Exception as e:
        logger.warning("TTS 合成失败: {}", e)
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
    return Response(content=audio, media_type=media_type)


@router.post("/voice/transcribe")
async def voice_transcribe(request: Request):
    from core.voice import get_asr
    asr = get_asr()
    if not asr.available():
        return JSONResponse({"ok": False, "error": "ASR 未配置"})
    try:
        body = await request.body()
        params = json.loads(body.decode("utf-8"))
        b64 = params.get("audio_base64", "")
        if not b64:
            return JSONResponse({"ok": False, "error": "请提供 audio_base64 参数"})
        text = await asr.transcribe_base64(b64, "wav")
        return {"ok": True, "text": text}
    except Exception as e:
        logger.error("voice_transcribe: {}", e)
        return JSONResponse({"ok": False, "error": str(e)})


@router.post("/voice/utter")
async def voice_utter(request: Request):
    """编排入口：文本(语音转写后/文字输入) → SSE 事件流。

    事件：task_state / content_delta / question / error / done。
    question 事件后需操作者回答：POST /api/voice/answer {session_id, text}。
    """
    from core.orchestrator.control import StopController
    from core.orchestrator.pipeline import run_pipeline
    from core.orchestrator.session import Session
    body = await request.body()
    try:
        params = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        return JSONResponse({"ok": False, "error": "无效 JSON"}, status_code=400)
    text = (params.get("text") or "").strip()
    if not text:
        return JSONResponse({"ok": False, "error": "缺少 text 参数"}, status_code=400)
    messages = params.get("messages")
    if not isinstance(messages, list):
        messages = None

    session = Session()
    controller = StopController()
    state.register(session, controller)
    events: asyncio.Queue = asyncio.Queue()
    runner = asyncio.ensure_future(run_pipeline(text, session, events, controller, messages=messages))

    async def event_stream():
        getter = asyncio.ensure_future(events.get())
        try:
            while True:
                done, _ = await asyncio.wait({runner, getter}, return_when=asyncio.FIRST_COMPLETED)
                if getter in done:
                    evt = getter.result()
                    yield _sse(evt)
                    if evt["type"] == "done":
                        break
                    getter = asyncio.ensure_future(events.get())  # 取下一个事件
                if runner in done:
                    # runner 提前结束（异常兜底），避免客户端永久等待
                    if not events.empty():
                        continue
                    exc = runner.exception()
                    if exc is not None:
                        yield _sse({"type": "error", "message": f"编排异常: {exc}"})
                    yield _sse({"type": "done"})
                    break
        finally:
            getter.cancel()
            runner.cancel()
            await asyncio.gather(getter, runner, return_exceptions=True)
            state.persist(session, state.session_ts.get(session.id))
            state.cleanup(session.id)  # done/error/客户端断开时不再被引用

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/voice/answer")
async def voice_answer(request: Request):
    """投递操作者对澄清/确认问题的回答，解除 pipeline 的 ask() 阻塞。"""
    body = await request.body()
    try:
        params = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        return JSONResponse({"ok": False, "error": "无效 JSON"}, status_code=400)
    session = state.get_session(params.get("session_id", ""))
    channel = getattr(session, "channel", None) if session else None
    if channel is None:
        return JSONResponse({"ok": False, "error": "会话不存在或未在等待回答"}, status_code=404)
    channel.answer(str(params.get("text") or ""))
    return {"ok": True}


@router.post("/task/{session_id}/stop")
async def task_stop(session_id: str):
    """停止该会话的整个任务（CancellationToken → executor/子进程中止）。"""
    ctrl = state.get_controller(session_id)
    if ctrl:
        ctrl.stop_task()
    return {"ok": True, "ack": "stop"}
