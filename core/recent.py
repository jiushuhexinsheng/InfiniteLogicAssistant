# -*- coding: utf-8 -*-
"""最近对话轮次（滚动缓冲，供桌面球迷你面板 /api/session/recent）"""
import json
from datetime import datetime

from core.config import ROOT_DIR

RECENT_FILE = ROOT_DIR / "data" / "recent_turns.json"
MAX_TURNS = 20


def list_turns() -> list:
    if not RECENT_FILE.exists():
        return []
    try:
        return json.loads(RECENT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def append_turn(user: str, assistant: str, tools: list[str] | None = None, source: str = "text") -> None:
    turns = list_turns()
    turns.append({
        "user": user,
        "assistant": assistant,
        "tools": tools or [],
        "source": source,
        "ts": datetime.now().isoformat(timespec="seconds"),
    })
    turns = turns[-MAX_TURNS:]
    RECENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    RECENT_FILE.write_text(json.dumps(turns, ensure_ascii=False, indent=2), encoding="utf-8")
