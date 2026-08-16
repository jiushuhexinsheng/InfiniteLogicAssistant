# -*- coding: utf-8 -*-
"""无限逻辑·语音助手 — FastAPI 异步服务（静态托管 + /api/* + SSE 聊天 + 编排管线）"""
import asyncio
import json
import mimetypes
import threading
import time
import webbrowser
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from core.config import (
    cfg, ensure_dirs, is_llm_configured, is_asr_configured, is_tts_enabled,
    resolve_llm_profile, resolve_asr_profile, resolve_tts_profile, ROOT_DIR,
)
from core.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时连接 MCP server 并注册其工具
    try:
        from core.mcp.manager import get_mcp_manager
        await get_mcp_manager().start_all()
    except Exception as e:
        logger.warning("MCP 启动失败: {}", e)
    # 启动定时调度（到点触发无人值守执行）
    try:
        from core.scheduler.runner import run_scheduled
        from core.scheduler.scheduler import get_scheduler
        sched = get_scheduler()
        sched.set_on_fire(run_scheduled)
        await sched.start()
    except Exception as e:
        logger.warning("定时调度启动失败: {}", e)
    # 启动时按需重建 RAG 索引（best-effort）
    try:
        if cfg("rag.auto_index", True):
            from core.rag import maybe_rebuild_index
            await maybe_rebuild_index()
    except Exception as e:
        logger.warning("RAG 索引构建失败: {}", e)
    yield
    try:
        from core.scheduler.scheduler import get_scheduler
        await get_scheduler().stop()
    except Exception:
        pass
    try:
        from core.mcp.manager import get_mcp_manager
        await get_mcp_manager().stop_all()
    except Exception:
        pass


app = FastAPI(title="无限逻辑·语音助手", lifespan=lifespan)

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
        "tts_available": is_tts_enabled(),
        "tts_profile": resolve_tts_profile()[0],
        "tts_voice": resolve_tts_profile()[1].get("voice", ""),
        "tts_model": resolve_tts_profile()[1].get("model", ""),
        "wake_word": cfg("voice.wake_word", {}),
        "vad": cfg("voice.vad", {}),
    }


@app.post("/api/tts")
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
    if not is_tts_enabled():
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


@app.get("/api/tools")
async def tools_list():
    """工具清单：后端 @tool 注册中心的 OpenAI schema 数组（供控制台展示）。"""
    from core.tools import TOOLS
    return {"ok": True, "tools": TOOLS.schemas()}


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


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# ── /api/tools/call：单工具执行（前端"重试失败工具"用）──
# 编排会话与停止控制器注册表（key = session_id）
_sessions: dict[str, "Session"] = {}
_controllers: dict[str, "StopController"] = {}


@app.post("/api/voice/utter")
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
    _sessions[session.id] = session
    _controllers[session.id] = controller
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

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/voice/answer")
async def voice_answer(request: Request):
    """投递操作者对澄清/确认问题的回答，解除 pipeline 的 ask() 阻塞。"""
    body = await request.body()
    try:
        params = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        return JSONResponse({"ok": False, "error": "无效 JSON"}, status_code=400)
    session = _sessions.get(params.get("session_id", ""))
    channel = getattr(session, "channel", None) if session else None
    if channel is None:
        return JSONResponse({"ok": False, "error": "会话不存在或未在等待回答"}, status_code=404)
    channel.answer(str(params.get("text") or ""))
    return {"ok": True}


@app.post("/api/task/{session_id}/stop")
async def task_stop(session_id: str):
    """停止该会话的整个任务（CancellationToken → executor/子进程中止）。"""
    ctrl = _controllers.get(session_id)
    if ctrl:
        ctrl.stop_task()
    return {"ok": True, "ack": "stop"}


@app.get("/api/env")
async def env():
    from core.execution.envprobe import read_environment_md
    return {"ok": True, "content": await read_environment_md()}


@app.get("/api/memory")
async def memory_list():
    from core.memory.context import get_facts_store
    return {"ok": True, "facts": await get_facts_store().all()}


@app.delete("/api/memory/{topic}")
async def memory_delete(topic: str):
    from core.memory.context import get_facts_store
    await get_facts_store().delete(topic)
    return {"ok": True}


# ── 定时任务（P3）──
@app.get("/api/schedules")
async def schedules_list():
    from core.scheduler.scheduler import get_scheduler
    return {"ok": True, "schedules": [asdict(s) for s in get_scheduler().list()]}


@app.post("/api/schedules")
async def schedules_add(request: Request):
    from core.scheduler.scheduler import get_scheduler
    body = await request.body()
    try:
        params = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        return JSONResponse({"ok": False, "error": "无效 JSON"}, status_code=400)
    cron = (params.get("cron") or "").strip()
    prompt = (params.get("prompt") or "").strip()
    if not cron or not prompt:
        return JSONResponse({"ok": False, "error": "cron 与 prompt 必填"}, status_code=400)
    sc = get_scheduler().add(cron, prompt)
    return {"ok": True, "schedule": asdict(sc)}


@app.delete("/api/schedules/{sid}")
async def schedules_delete(sid: str):
    from core.scheduler.scheduler import get_scheduler
    get_scheduler().remove(sid)
    return {"ok": True}


@app.post("/api/tools/call")
async def tools_call(request: Request):
    from core.tools import TOOLS
    body = await request.body()
    try:
        params = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        return JSONResponse({"ok": False, "error": "无效 JSON"}, status_code=400)
    name = params.get("name", "")
    args = params.get("args") or {}
    if not isinstance(name, str) or not name:
        return JSONResponse({"ok": False, "error": "缺少工具名 name"}, status_code=400)
    if not isinstance(args, dict):
        return JSONResponse({"ok": False, "error": "args 必须为 JSON 对象"}, status_code=400)
    if not TOOLS.has(name):
        return JSONResponse({"ok": False, "error": f"未知工具: {name}"}, status_code=404)
    try:
        result = await TOOLS.acall(name, args)
    except Exception as exc:
        logger.error("tools_call {}: {}", name, exc)
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    status = "error" if result.startswith("Error") else "ok"
    return {"ok": True, "status": status, "output": result}


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
