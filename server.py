# -*- coding: utf-8 -*-
"""无限逻辑·语音助手 — FastAPI 异步服务（静态托管 + /api/*）"""
import asyncio
import json
import threading
import time
import webbrowser
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from core.config import (
    cfg, ensure_dirs, is_llm_configured, is_asr_configured,
    resolve_llm_profile, resolve_asr_profile, ROOT_DIR,
)
from core.logger import logger

app = FastAPI(title="无限逻辑·语音助手")

WEB_DIST_DIR = ROOT_DIR / "web" / "dist"


@app.get("/api/ping")
async def ping():
    from datetime import datetime
    return {"ok": True, "time": datetime.now().isoformat()}


@app.get("/api/config")
async def config():
    return {
        "llm_available": is_llm_configured(),
        "llm_profile": resolve_llm_profile()[0],
        "asr_available": is_asr_configured(),
        "asr_profile": resolve_asr_profile()[0],
        "wake_word": cfg("voice.wake_word", {}),
        "vad": cfg("voice.vad", {}),
    }


@app.post("/api/voice/transcribe")
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


# ── /api/ai/chat：过渡期同步调用旧 LLM（Phase C 改 SSE）──
def _chat_sync(params: dict) -> dict:
    from core.llm import get_llm
    llm = get_llm()
    if not llm.available():
        return {"ok": False, "error": "LLM 未配置"}
    try:
        result = llm._call(params.get("messages", []))
        return {"ok": True, "text": result}
    except Exception as e:
        logger.error("ai_chat 失败: {} | {} {}", e, llm.provider, llm.model)
        return {"ok": False, "error": str(e)}


@app.post("/api/ai/chat")
async def ai_chat(request: Request):
    body = await request.body()
    try:
        params = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        return JSONResponse({"ok": False, "error": "无效 JSON"}, status_code=400)
    return await asyncio.to_thread(_chat_sync, params)


# ── 静态托管 web/dist ──
def _mount_static():
    if not WEB_DIST_DIR.is_dir():
        return
    app.mount("/", StaticFiles(directory=str(WEB_DIST_DIR), html=True), name="static")


_mount_static()


def start_server(host: str = "", port: int = 0, open_browser: bool = True):
    import uvicorn
    host = host or cfg("server.host", "127.0.0.1")
    port = port or cfg("server.port", 8520)
    open_browser = open_browser and cfg("server.open_browser", True)
    ensure_dirs()
    url = f"http://{host}:{port}"
    if WEB_DIST_DIR.is_dir():
        logger.info("服务已启动: {} （前端已构建）", url)
    else:
        logger.info("服务已启动: {} （未检测到 web/dist，请先构建前端）", url)
    if open_browser:
        threading.Thread(target=lambda: (time.sleep(1), webbrowser.open(url)), daemon=True).start()
    uvicorn.run(app, host=host, port=port, log_level="warning")
