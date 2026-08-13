# -*- coding: utf-8 -*-
"""后端运行器 — 探测 8520；未运行则在进程内线程起 uvicorn（自包含，便于打包）"""
import sys
import threading
import traceback
from pathlib import Path

from desktop_py import api


def _err_log():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "backend_err.log"
    return Path(__file__).resolve().parent.parent / "data" / "backend_err.log"


def _run_backend():
    try:
        import uvicorn
        import server  # noqa: F401  (ROOT 已在 sys.path)
        uvicorn.run(server.app, host="127.0.0.1", port=8520, log_level="warning")
    except Exception:
        try:
            log = _err_log()
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text(traceback.format_exc(), encoding="utf-8")
        except Exception:
            pass


def ensure_backend() -> bool:
    if api.ping():
        return True
    try:
        threading.Thread(target=_run_backend, daemon=True).start()
        return True
    except Exception:
        return False
