# -*- coding: utf-8 -*-
"""全局助手状态（供桌面球/前端轮询 /api/status）"""
import time

_status = {"state": "idle", "activity": "", "summary": "", "updated": 0.0}


def set_status(state: str | None = None, activity: str | None = None, summary: str | None = None) -> None:
    if state:
        _status["state"] = state
    if activity is not None:
        _status["activity"] = activity
    if summary is not None:
        _status["summary"] = summary
    _status["updated"] = time.time()


def get_status() -> dict:
    return dict(_status)
