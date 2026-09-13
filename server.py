# -*- coding: utf-8 -*-
"""无限逻辑·语音助手 — FastAPI 装配（lifespan + 认证/CORS + 路由挂载 + 静态托管）

Unlimited Logic voice assistant — FastAPI assembly (lifespan + auth/CORS + router mounting + static hosting)."""
import mimetypes
import threading
import time
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from core import config as config
from core.api import history, library, memory, providers, schedule, sessions, settings, tools, voice
from core.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动/关闭统一的应用上下文容器（MCP / 调度 / RAG 索引 / LLM 连接池）。

    Application lifespan: start/shutdown the unified app context container (MCP / scheduler / RAG index / LLM connection pool).
    """
    # 应用上下文容器统一启动/关闭（MCP / 定时调度 / RAG 索引 / LLM 连接池）
    from core.container import AppContext
    await AppContext.get().start()
    yield
    await AppContext.get().shutdown()


app = FastAPI(title="无限逻辑·语音助手", lifespan=lifespan)

# ── 安全：非 localhost 绑定必须配 api_token；CORS 默认禁止跨域 ──
def _is_localhost(host: str) -> bool:
    """判断主机名是否为本地回环地址。

    Return whether the host is a local loopback address.
    """
    return host in ("", "127.0.0.1", "localhost", "::1")


@app.middleware("http")
async def _auth_middleware(request: Request, call_next):
    """认证中间件：配置了 api_token 时，校验所有 /api/* 请求的 X-API-Token。

    Auth middleware: when api_token is configured, validate the X-API-Token header on every /api/* request.
    """
    token = config.settings.server.api_token
    # 配置了 token 时，所有 /api/* 请求都需携带正确的 X-API-Token（静态资源放行）
    if token and request.url.path.startswith("/api/"):
        if request.headers.get("x-api-token") != token:
            return JSONResponse({"ok": False, "error": "未授权：需要正确的 X-API-Token"}, status_code=401)
    return await call_next(request)


_cors_origins = config.settings.server.cors_origins
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _validate_bind(host: str, token: str) -> None:
    """非 localhost 绑定必须配 api_token，否则拒绝启动（避免无认证 RCE）。

    Reject non-localhost binds without an api_token to prevent unauthenticated RCE.
    """
    # 验证绑定地址（非 localhost 需配 token），防止无认证 RCE 漏洞
    if not _is_localhost(host) and not token:
        raise RuntimeError(
            "拒绝在非 localhost 地址启动：未配置 server.api_token。"
            "公开绑定会暴露可执行任意命令的 API。请先在 config.yaml 设置 api_token。"
        )


WEB_DIST_DIR = config.ROOT_DIR / "web" / "dist"

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

# 挂载各域路由
app.include_router(voice.router, prefix="/api")
app.include_router(tools.router, prefix="/api")
app.include_router(memory.router, prefix="/api")
app.include_router(schedule.router, prefix="/api")
app.include_router(history.router, prefix="/api")
app.include_router(library.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(providers.router, prefix="/api")


# ── 静态托管 web/dist + SPA 兜底 ──
def _resolve_dist(path: str):
    """把 URL 路径安全解析到 dist 内；返回目标 Path 或 None。

    Safely resolve a URL path inside dist; return the target Path or None.
    """
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
    """SPA 兜底路由：托管静态文件，未知 /api 路径返回 404，非 api 导航回退 index.html。

    SPA fallback route: serve static files, return 404 for unknown /api paths, and fall back to index.html for non-API navigation.
    """
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
    """启动 uvicorn 服务；可指定主机/端口，并可选择自动打开浏览器。

    Start the uvicorn server; the host/port can be specified, and the browser can be opened automatically.
    """
    # 验证绑定地址（非 localhost 需配 token），防止无认证 RCE 漏洞
    # 初始化目录和 url，启动 uvicorn 服务
    import uvicorn
    host = host or config.settings.server.host
    port = port or config.settings.server.port
    open_browser = open_browser and config.settings.server.open_browser
    _validate_bind(host, config.settings.server.api_token)
    config.ensure_dirs()
    url = f"http://{host}:{port}"
    if WEB_DIST_DIR.is_dir():
        logger.info("服务已启动: {} （前端已构建）", url)
    else:
        logger.info("服务已启动: {} （未检测到 web/dist，请先构建前端）", url)
    if open_browser:
        def _open_browser() -> None:
            time.sleep(1)
            webbrowser.open(url)
        threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run(app, host=host, port=port, log_level="warning")
