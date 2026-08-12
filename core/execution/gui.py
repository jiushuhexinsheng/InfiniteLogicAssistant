# -*- coding: utf-8 -*-
"""GUI 自动化 — 启动应用/窗口/点击/输入/截图（pyautogui/pygetwindow，懒加载优雅降级）"""
import shutil
import subprocess
from typing import Optional


def _launch_command(app_name: str) -> Optional[str]:
    """把应用名解析为可启动命令：which 命中 / 常见别名。"""
    exe = shutil.which(app_name)
    if exe:
        return exe
    if app_name in ("notepad", "记事本"):
        return "notepad"
    return None


async def gui_activate(app_name: str) -> str:
    """打开已安装应用（免确认）。"""
    cmd = _launch_command(app_name)
    if not cmd:
        return f"Error: 未找到应用 {app_name}"
    subprocess.Popen([cmd], shell=True)
    return f"已启动 {app_name}"


async def list_windows() -> str:
    try:
        import pygetwindow as gw
    except ImportError:
        return "Error: 需要 pygetwindow（pip install pygetwindow）"
    wins = [w.title for w in gw.getAllWindows() if w.title]
    return "\n".join(wins[:50]) or "无可见窗口"


async def gui_click(x: int, y: int) -> str:
    try:
        import pyautogui
    except ImportError:
        return "Error: 需要 pyautogui"
    pyautogui.click(x, y)
    return f"已点击 ({x},{y})"


async def gui_type(text: str) -> str:
    try:
        import pyautogui
    except ImportError:
        return "Error: 需要 pyautogui"
    pyautogui.typewrite(text)
    return f"已输入：{text}"


async def gui_screenshot(path: str) -> str:
    try:
        import pyautogui
    except ImportError:
        return "Error: 需要 pyautogui"
    img = pyautogui.screenshot()
    img.save(path)
    return f"截图已保存 {path}"
