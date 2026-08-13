# -*- coding: utf-8 -*-
"""桌面悬浮球入口 — 起/探测后端 → 小球窗口 + 托盘"""
import sys
from pathlib import Path

# 脚本方式运行（desktop_py/main.py）时把项目根加入 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from desktop_py import backend_runner
from desktop_py.ball import BallWindow
from desktop_py.mini_panel import MiniPanel
from desktop_py.tray import Tray


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    if not backend_runner.ensure_backend():
        print("[错误] 后端启动失败，请先运行: py main.py serve")

    panel = MiniPanel()
    ball = BallWindow(panel)
    ball.show()
    tray = Tray(ball, app)  # 保持引用防 GC

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
