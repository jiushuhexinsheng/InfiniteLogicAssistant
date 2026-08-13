# -*- coding: utf-8 -*-
"""悬浮球窗口 — 无边框透明置顶圆窗，QPainter 画状态环 + 图标"""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

from desktop_py import api, theme

_CLICK_DELAY = 250  # 区分单击/双击的等待毫秒


class BallWindow(QWidget):
    def __init__(self):
        super().__init__()
        # Qt.SubWindow 会使无父窗口的置顶窗不显示，必须用 Qt.Window
        self.setWindowFlags(
            Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(96, 96)
        # 默认位置：主屏右下角
        screen = QGuiApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(geo.right() - 96 - 40, geo.bottom() - 96 - 40)
        self.state = "idle"
        self._drag_pos = None
        self._moved = False
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self._on_single_click)

        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start(1000)

    def _poll(self):
        st = api.get_status()
        if st and st.get("state"):
            self.state = st.get("state", "idle")
            self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(5, 5, -5, -5)
        color = QColor(theme.STATUS_COLORS.get(self.state, theme.STATUS_COLORS["idle"]))
        # 球体
        p.setBrush(QColor(theme.BODY_COLOR))
        p.setPen(QPen(color, 3))
        p.drawEllipse(rect)
        # 状态图标（emoji）
        p.setPen(QColor(theme.STATUS_COLORS.get(self.state, theme.STATUS_COLORS["idle"])))
        p.setFont(QFont("Segoe UI Emoji", 26))
        p.drawText(rect, Qt.AlignCenter, theme.STATUS_ICONS.get(self.state, "◌"))
        p.end()

    # ── 拖拽 + 单击/双击 ──
    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._drag_pos = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._moved = False

    def mouseMoveEvent(self, ev):
        if self._drag_pos is not None and (ev.buttons() & Qt.LeftButton):
            self.move(ev.globalPosition().toPoint() - self._drag_pos)
            self._moved = True

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            if not self._moved and not self._click_timer.isActive():
                self._click_timer.start(_CLICK_DELAY)
            self._drag_pos = None

    def mouseDoubleClickEvent(self, ev):
        self._click_timer.stop()
        api.toggle_voice()

    def _on_single_click(self):
        api.open_console()
