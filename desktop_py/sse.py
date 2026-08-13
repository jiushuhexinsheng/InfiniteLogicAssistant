# -*- coding: utf-8 -*-
"""SSE 工作线程 — 调 /api/voice/utter，流式回 UI；question 暂停等待回答"""
import json
import threading
import urllib.request

from PySide6.QtCore import QThread, Signal

BASE = "http://127.0.0.1:8520"


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
        try:
            data = json.dumps({"text": self._text}).encode("utf-8")
            req = urllib.request.Request(
                f"{BASE}/api/voice/utter", data=data,
                headers={"Content-Type": "application/json"}, method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=120)
            buf = b""
            while True:
                chunk = resp.read(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n\n" in buf:
                    block, buf = buf.split(b"\n\n", 1)
                    self._parse(block.decode("utf-8", errors="replace"))
            self.task_done.emit()
        except Exception as e:
            self.error.emit(str(e))

    def _parse(self, block: str):
        for line in block.splitlines():
            if not line.startswith("data: "):
                continue
            try:
                evt = json.loads(line[6:])
            except Exception:
                continue
            t = evt.get("type")
            if t == "content_delta":
                self.content.emit(evt.get("text", ""))
            elif t == "task_state" and evt.get("state") == "done" and evt.get("summary"):
                # 任务型回复在 done 事件里携带 summary
                self.content.emit("\n" + evt["summary"])
            elif t == "question":
                self._session_id = evt.get("session_id", "")
                self.question.emit(evt.get("question", ""), self._session_id)
                # 等待面板回答后继续
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
            data = json.dumps({"session_id": self._session_id, "text": text}).encode("utf-8")
            req = urllib.request.Request(
                f"{BASE}/api/voice/answer", data=data,
                headers={"Content-Type": "application/json"}, method="POST",
            )
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass
