# -*- coding: utf-8 -*-
"""后端运行器 — 探测 8520；未运行则在进程内线程起 uvicorn（自包含，便于打包）"""
import threading

from desktop_py import api


def _run_backend():
    import uvicorn
    import server  # noqa: F401  (ROOT 已在 sys.path)
    uvicorn.run(server.app, host="127.0.0.1", port=8520, log_level="warning")


def ensure_backend() -> bool:
    if api.ping():
        return True
    try:
        threading.Thread(target=_run_backend, daemon=True).start()
        return True
    except Exception:
        return False
