# -*- coding: utf-8 -*-
"""无限逻辑·语音助手 — FastAPI 异步服务（静态托管 + /api/* + SSE 聊天）"""
import json
import mimetypes
import threading
import time
import webbrowser
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from core.config import (
    cfg, ensure_dirs, is_llm_configured, is_asr_configured,
    resolve_llm_profile, resolve_asr_profile, ROOT_DIR,
)
from core.logger import logger

app = FastAPI(title="无限逻辑·语音助手")

WEB_DIST_DIR = ROOT_DIR / "web" / "dist"

# Vosk 模型等特殊扩展名的 content-type（FileResponse 的 mimetypes 不认识）
_EXTRA_TYPES = {
    ".wasm": "application/wasm",
    ".mdl": "application/octet-stream",
    ".fst": "application/octet-stream",
    ".int": "application/octet-stream",
    ".mat": "application/octet-stream",
    ".dubm": "application/octet-stream",
    ".ie": "application/octet-stream",
    ".stats": "application/octet-stream",
    ".conf": "text/plain; charset=utf-8",
    ".tar.gz": "application/octet-stream",
}
for _ext, _ct in _EXTRA_TYPES.items():
    mimetypes.add_type(_ct, _ext)


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


# ── /api/ai/chat：SSE 流式（ReAct + 工具）──
def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.post("/api/ai/chat")
async def ai_chat(request: Request):
    body = await request.body()
    try:
        params = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        return JSONResponse({"ok": False, "error": "无效 JSON"}, status_code=400)
    messages = params.get("messages", [])

    if not is_llm_configured():
        return JSONResponse({"ok": False, "error": "LLM 未配置"})

    from core.agent import run_agent

    async def event_stream():
        async for evt in run_agent(messages):
            yield _sse(evt)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── 静态托管 web/dist + SPA 兜底 ──
def _resolve_dist(path: str):
    """把 URL 路径安全解析到 dist 内；返回目标 Path 或 None。"""
    clean = path.lstrip("/").split("?")[0]
    try:
        rel = Path(clean)
        target = (WEB_DIST_DIR / rel).resolve()
        target.relative_to(WEB_DIST_DIR.resolve())
        return target
    except (ValueError, OSError):
        return None


@app.get("/{full_path:path}")
async def spa_handler(full_path: str):
    if full_path.startswith("api/"):
        return JSONResponse({"ok": False, "error": f"未知接口: /{full_path}"}, status_code=404)
    if not WEB_DIST_DIR.is_dir():
        return JSONResponse({"ok": False, "error": "前端未构建（web/dist 不存在）"}, status_code=404)

    target = _resolve_dist(full_path)
    if target is None:
        return JSONResponse({"ok": False, "error": "禁止访问"}, status_code=403)

    if target.is_dir():
        target = target / "index.html"
    if target.is_file():
        return FileResponse(str(target))
    # SPA 兜底：非 /api 导航回退 index.html
    idx = WEB_DIST_DIR / "index.html"
    if idx.is_file():
        return FileResponse(str(idx))
    return JSONResponse({"ok": False, "error": "页面不存在"}, status_code=404)


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
