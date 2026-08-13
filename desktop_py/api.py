# -*- coding: utf-8 -*-
"""薄 HTTP 客户端 — 与后端 8520 通信（stdlib，无第三方依赖）"""
import json
import urllib.request

BASE = "http://127.0.0.1:8520"


def _get(path: str):
    try:
        with urllib.request.urlopen(f"{BASE}{path}", timeout=3) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def _post(path: str):
    try:
        req = urllib.request.Request(f"{BASE}{path}", method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def ping() -> bool:
    return bool(_get("/api/ping"))


def get_status() -> dict:
    return _get("/api/status") or {}


def get_recent() -> list:
    data = _get("/api/session/recent")
    return (data or {}).get("turns", [])


def toggle_voice() -> bool:
    data = _post("/api/voice/toggle")
    return bool(data and data.get("running"))


def open_console() -> None:
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    QDesktopServices.openUrl(QUrl(f"{BASE}/console"))
