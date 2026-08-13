# -*- coding: utf-8 -*-
"""SSE 工作线程 — 调 /api/voice/utter，流式回 UI；question 暂停等待回答"""
import json
import threading
from pathlib import Path

import requests
from PySide6.QtCore import QThread, Signal

BASE = "http://127.0.0.1:8520"
_DEBUG_LOG = Path(__file__).resolve().parent.parent / "data" / "worker.log"


def _debug(msg: str) -> None:
    try:
        _DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
        with _DEBUG_LOG.open("a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


class UtterWorker(QThread):
    content = Signal(str)          # 回复增量
    question = Signal(str, str)    # 澄清/确认问题, session_id
    task_done = Signal()
    error = Signal(str)

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self._text = text
        self._session_id = ""
        self._answer_event = threading.Event()
        self._answer_text = ""

    def run(self):
        _debug(f"[worker] start text={self._text}")
        try:
            resp = requests.post(f"{BASE}/api/voice/utter", json={"text": self._text},
                                 stream=True, timeout=120)
            _debug(f"[worker] status={resp.status_code}")
            for raw in resp.iter_lines():
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="replace")
                if line.startswith("data: "):
                    self._parse(line[6:].strip())
            self.task_done.emit()
            _debug("[worker] done")
        except Exception as e:
            _debug(f"[worker] ERROR {e!r}")
            self.error.emit(str(e))

    def _parse(self, data: str):
        try:
            evt = json.loads(data)
        except Exception as e:
            _debug(f"[worker] parse err {e!r}: {data[:80]}")
            return
        t = evt.get("type")
        _debug(f"[worker] evt {t}")
        if t == "content_delta":
            self.content.emit(evt.get("text", ""))
        elif t == "task_state" and evt.get("state") == "done" and evt.get("summary"):
            self.content.emit("\n" + evt["summary"])
        elif t == "question":
            self._session_id = evt.get("session_id", "")
            self.question.emit(evt.get("question", ""), self._session_id)
            self._answer_event.clear()
            self._answer_event.wait()
            self._post_answer(self._answer_text)
        elif t == "error":
            self.error.emit(evt.get("message", "出错"))
            self._answer_event.set()
        elif t == "done":
            self._answer_event.set()

    def answer(self, text: str):
        self._answer_text = text
        self._answer_event.set()

    def _post_answer(self, text: str):
        try:
            requests.post(f"{BASE}/api/voice/answer",
                          json={"session_id": self._session_id, "text": text}, timeout=10)
        except Exception:
            pass
