# -*- coding: utf-8 -*-
"""后端运行器 — 探测 8520；若未运行则拉起后端子进程"""
import subprocess
import sys
from pathlib import Path

from desktop_py import api


def ensure_backend() -> bool:
    if api.ping():
        return True
    root = Path(__file__).resolve().parent.parent
    try:
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        subprocess.Popen(
            [sys.executable, str(root / "main.py"), "serve"],
            cwd=str(root), **kwargs,
        )
        return True
    except Exception:
        return False
