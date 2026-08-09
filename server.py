# -*- coding: utf-8 -*-
"""
无限逻辑·语音助手 — HTTP API 服务
"""
import json
import mimetypes
import shutil
import threading
import time
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from core.config import cfg, ensure_dirs, is_llm_configured, is_asr_configured, resolve_llm_profile, resolve_asr_profile, ROOT_DIR
from core.logger import logger


class APIHandler:
    """语音助手 API 处理器"""

    def ai_chat(self, params: dict) -> dict:
        """通用 LLM 对话（悬浮球助手使用）"""
        from core.llm import get_llm
        llm = get_llm()
        if not llm.available():
            return {"ok": False, "error": "LLM 未配置"}
        try:
            messages = params.get("messages", [])
            logger.info("ai_chat 请求，{} 条消息", len(messages))
            result = llm._call(messages)
            logger.info("ai_chat 返回 {} 字", len(result or ""))
            return {"ok": True, "text": result}
        except Exception as e:
            logger.error("ai_chat 失败: {} | provider={} model={}", e, llm.provider, llm.model)
            logger.debug("ai_chat 堆栈", exc_info=True)
            return {"ok": False, "error": str(e)}

    def voice_transcribe(self, body: bytes) -> dict:
        from core.voice import get_asr
        asr = get_asr()
        if not asr.available():
            return {"ok": False, "error": "ASR 未配置"}
        try:
            # JSON 体传 audio_base64（16kHz mono WAV）
            if body:
                try:
                    params = json.loads(body.decode("utf-8"))
                    b64 = params.get("audio_base64", "")
                    if b64:
                        text = asr.transcribe_base64(b64, "wav")
                        return {"ok": True, "text": text}
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass
            return {"ok": False, "error": "请提供 audio_base64 参数"}
        except Exception as e:
            logger.error("voice_transcribe: {}", e)
            return {"ok": False, "error": str(e)}

    def config(self) -> dict:
        return {
            "llm_available": is_llm_configured(),
            "llm_profile": resolve_llm_profile()[0],
            "asr_available": is_asr_configured(),
            "asr_profile": resolve_asr_profile()[0],
            "wake_word": cfg("voice.wake_word", {}),
            "vad": cfg("voice.vad", {}),
        }


# ─── 静态文件服务 ───

WEB_DIST_DIR = ROOT_DIR / "web" / "dist"
_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".mjs": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".wasm": "application/wasm",
    ".mdl": "application/octet-stream",
    ".fst": "application/octet-stream",
    ".int": "application/octet-stream",
    ".mat": "application/octet-stream",
    ".dubm": "application/octet-stream",
    ".ie": "application/octet-stream",
    ".stats": "application/octet-stream",
    ".conf": "text/plain; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
}


def _send_file(handler, path: Path, content_type: str) -> None:
    """流式发送文件，避免大文件整块读入内存（如 Vosk 模型 ~40MB）"""
    try:
        size = path.stat().st_size
        f = path.open("rb")
    except Exception:
        handler._send_json({"ok": False, "error": "读取失败"}, 500)
        return
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(size))
    handler.end_headers()
    try:
        shutil.copyfileobj(f, handler.wfile)
    finally:
        f.close()


def _serve_static(handler, path: str) -> bool:
    """托管 web/dist 前端静态资源，供 'python main.py serve' 单命令启动。

    返回 True 表示已处理（页面/资源已输出），False 表示非前端路径（未匹配）。
    """
    if not WEB_DIST_DIR.is_dir():
        return False
    # 去掉查询串
    clean = path.split("?")[0]
    # 规范化：空路径/目录 → index.html
    if clean in ("", "/"):
        clean = "/index.html"
    # 解析到 dist 根内，防止路径穿越
    try:
        rel = Path(clean.lstrip("/"))
        target = (WEB_DIST_DIR / rel).resolve()
        target.relative_to(WEB_DIST_DIR.resolve())
    except (ValueError, OSError):
        handler._send_json({"ok": False, "error": "禁止访问"}, 403)
        return True
    if target.is_dir():
        target = target / "index.html"
    if target.is_file():
        content_type = (_CONTENT_TYPES.get(target.suffix.lower())
                        or mimetypes.guess_type(target.name)[0]
                        or "application/octet-stream")
        _send_file(handler, target, content_type)
        return True
    # 前端 SPA 路由兜底：仅对导航请求(Accept: text/html)回退 index.html；
    # 资源请求(script/fetch)与 /api 路径返回真实 404，避免 404 被吞成 HTML
    accept = handler.headers.get("Accept", "")
    if "text/html" in accept and not clean.startswith("/api"):
        target = (WEB_DIST_DIR / "index.html").resolve()
        if target.is_file():
            _send_file(handler, target, "text/html; charset=utf-8")
            return True
    return False


# ─── HTTP Server ───

api = APIHandler()


class AgentHTTPHandler(BaseHTTPRequestHandler):
    """API 路由处理器（前端与 API 同源托管，无需 CORS 头）"""

    def log_message(self, format, *args):
        logger.debug("HTTP {} {}", self.command, args[0] if args else "")

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length else b""

    def do_GET(self):
        path = urlparse(self.path).path
        routes = {
            "/api/ping": lambda: {"ok": True, "time": datetime.now().isoformat()},
            "/api/config": lambda: api.config(),
        }
        handler = routes.get(path)
        if handler:
            return self._send_json(handler())
        # 非 API 路径 → 尝试托管 web/dist 前端页面
        if _serve_static(self, path):
            return
        return self._send_json({"ok": False, "error": f"未知接口: {path}"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        body = self._read_body()

        if path == "/api/voice/transcribe":
            return self._send_json(api.voice_transcribe(body))

        try:
            params = json.loads(body.decode("utf-8")) if body else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            return self._send_json({"ok": False, "error": "无效 JSON"}, 400)

        routes = {
            "/api/ai/chat": lambda: api.ai_chat(params),
        }
        handler = routes.get(path)
        if handler:
            return self._send_json(handler())
        return self._send_json({"ok": False, "error": f"未知接口: {path}"}, 404)


def start_server(host: str = "", port: int = 0, open_browser: bool = True):
    host = host or cfg("server.host", "127.0.0.1")
    port = port or cfg("server.port", 8520)
    open_browser = open_browser and cfg("server.open_browser", True)

    ensure_dirs()
    # ThreadingHTTPServer：避免单个慢请求（如 LLM 最长 60s）阻塞其他请求（静态文件/ASR）
    server = ThreadingHTTPServer((host, port), AgentHTTPHandler)
    url = f"http://{host}:{port}"
    if WEB_DIST_DIR.is_dir():
        logger.info("服务已启动: {} （前端已构建，直接访问即可）", url)
    else:
        logger.info("服务已启动: {} （未检测到 web/dist，前端请用 npm run dev 或先构建）", url)

    if open_browser:
        import webbrowser
        target = f"http://{host}:{port}"
        threading.Thread(target=lambda: (time.sleep(1), webbrowser.open(target)), daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("服务已停止")
        server.shutdown()
