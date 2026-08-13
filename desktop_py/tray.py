# -*- coding: utf-8 -*-
"""系统托盘 — 显示/隐藏球、打开控制台、退出"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from desktop_py import api


def _make_icon() -> QIcon:
    pm = QPixmap(32, 32)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#22d3ee"))
    p.setPen(Qt.NoPen)
    p.drawEllipse(4, 4, 24, 24)
    p.end()
    return QIcon(pm)


class Tray:
    def __init__(self, ball, app):
        self._tray = QSystemTrayIcon(_make_icon())
        self._tray.setToolTip("无限逻辑·悬浮球")
        menu = QMenu()
        menu.addAction("显示/隐藏悬浮球", lambda: ball.setVisible(not ball.isVisible()))
        menu.addAction("打开控制台", api.open_console)
        menu.addAction("退出", app.quit)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(
            lambda reason: ball.setVisible(True) if reason == QSystemTrayIcon.Trigger else None
        )
        self._tray.show()
