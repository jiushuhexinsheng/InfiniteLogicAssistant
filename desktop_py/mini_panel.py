# -*- coding: utf-8 -*-
"""迷你面板 — 最近对话列表 + 输入框，SSE 流式回复，question 可回答"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton, QVBoxLayout, QWidget,
)

from desktop_py import api
from desktop_py.sse import UtterWorker

QSS = """
QWidget { background: #0f172a; color: #e2e8f0; font-size: 13px; }
QListWidget { background: #0b1120; border: none; }
QLineEdit { background: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 6px; }
QPushButton { background: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 5px 10px; }
QPushButton:hover { color: #67e8f9; border-color: #67e8f9; }
"""


class MiniPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(320, 420)
        self.setStyleSheet(QSS)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        head = QHBoxLayout()
        self.status_label = QLabel("小逻")
        self.status_label.setStyleSheet("color: #67e8f9; font-weight: bold;")
        open_btn = QPushButton("控制台")
        open_btn.clicked.connect(api.open_console)
        close_btn = QPushButton("×")
        close_btn.clicked.connect(self.hide)
        head.addWidget(self.status_label)
        head.addStretch()
        head.addWidget(open_btn)
        head.addWidget(close_btn)
        layout.addLayout(head)

        self.list = QListWidget()
        layout.addWidget(self.list, 1)

        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("说点什么，回车发送…")
        self.input.returnPressed.connect(self.send)
        send_btn = QPushButton("发送")
        send_btn.clicked.connect(self.send)
        row.addWidget(self.input, 1)
        row.addWidget(send_btn)
        layout.addLayout(row)

        self._worker = None
        self._pending_answer = False
        self._stream_item = None
        self.refresh()

    def refresh(self):
        turns = api.get_recent()
        self.list.clear()
        for t in turns[-10:]:
            user = t.get("user", "")
            asst = t.get("assistant", "")
            tools = ", ".join(t.get("tools", []))
            text = f"你: {user}\n小逻: {asst}"
            if tools:
                text += f"\n🔧 {tools}"
            self.list.addItem(text)
        self.list.scrollToBottom()

    def send(self):
        text = self.input.text().strip()
        if not text:
            return
        # 等待回答问题 → 作为回答发送
        if self._pending_answer and self._worker:
            self._worker.answer(text)
            self._pending_answer = False
            self.input.clear()
            self._reset_input("说点什么，回车发送…")
            self.list.addItem(f"（回答）{text}")
            self.list.scrollToBottom()
            return
        if self._worker:
            return  # 上一个任务未结束
        self.input.clear()
        self.list.addItem(f"你: {text}")
        self.list.addItem("小逻: ")  # 流式回复目标
        self._stream_item = self.list.item(self.list.count() - 1)
        self.list.scrollToBottom()
        self._worker = UtterWorker(text, self)
        self._worker.content.connect(self._stream)
        self._worker.question.connect(self._on_question)
        self._worker.task_done.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _stream(self, t):
        if self._stream_item:
            self._stream_item.setText(self._stream_item.text() + t)
            self.list.scrollToBottom()

    def _on_question(self, q, sid):
        self.list.addItem(f"❓ {q}")
        self.list.scrollToBottom()
        self._pending_answer = True
        self._reset_input("输入回答后回车")

    def _on_done(self):
        self._worker = None
        self.refresh()

    def _on_error(self, msg):
        self.list.addItem(f"⚠ {msg}")
        self.list.scrollToBottom()
        self._worker = None
        self._reset_input("说点什么，回车发送…")

    def _reset_input(self, placeholder: str):
        self.input.setPlaceholderText(placeholder)
